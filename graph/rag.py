import json
import re
import textwrap
import threading
import time
from typing import Any, Callable, Optional

import ollama
import pandas as pd
from colorama import Fore
from langchain.prompts import ChatPromptTemplate
from langchain.schema import AIMessage
from langchain.schema.runnable import Runnable
from langchain.schema.runnable.config import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_ollama import ChatOllama
from loguru import logger as log
from platformdirs import user_config_path
from prompt_toolkit import PromptSession
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style

from graph.ops import GraphOps

RunnableFn = Callable[[dict[str, Any]], dict[str, Any]]


COMMAND_INFO = {
    ".help": "Shows this message",
    ".quit": "Exits to the command line",
    ".clear": "Clear history file",
}


class CommandLexer(Lexer):
    COMMANDS = re.compile(rf"({'|'.join(COMMAND_INFO.keys())})\b(.*)")

    def lex_document(self, document: Document) -> callable:
        text = document.text

        def get_line(lineno):
            tokens: StyleAndTextTuples = []
            cmd_match = self.COMMANDS.match(text)
            if cmd_match:
                tokens.append(("class:cmd", cmd_match.group(1)))
                tokens.append(("", cmd_match.group(2)))
            else:
                tokens.append(("", text))
            return tokens

        return get_line


class GraphRetrievalException(Exception):
    def __init__(self, message, query):
        self.query = query
        super().__init__(message)


class ContextAssemblerException(Exception):
    pass


class GraphRAG(Runnable):
    def __init__(
        self,
        schema: str,
        code_model: str = "phi4:latest",
        chat_model: str = "gemma3:latest",
        column_name: str = "embedding",
    ):
        self.schema = schema
        self.code_model = code_model
        self.chat_model = chat_model
        self.column_name = column_name

        self.ops = GraphOps(schema)
        self.ops.reindex_embeddings(column_name)

    def setup_llm_models(self):
        ollama_models = {m.model for m in ollama.list().models}

        for model in self.code_model, self.chat_model:
            if model not in ollama_models:
                log.warning("{}: ollama model not found, pulling...", model)
                ollama.pull(model)

    @property
    def code_llm(self) -> BaseChatModel:
        if not hasattr(self, "_code_llm"):
            self._code_llm = ChatOllama(model=self.code_model, temperature=0.0)

        return self._code_llm

    @property
    def chat_llm(self) -> BaseChatModel:
        if not hasattr(self, "_chat_llm"):
            self._chat_llm = ChatOllama(model=self.chat_model, temperature=0.2)

        return self._chat_llm

    @property
    def entities_prompt(self) -> ChatPromptTemplate:
        if not hasattr(self, "_entities_prompt"):
            tpl = textwrap.dedent(
                """
                You are an AI assistant analyzing a Bitcoin transaction graph. The graph contains Transaction nodes with properties: tx_id (string), tx_class (illicit/licit/unknown), and time_step (integer 1-49).

                Task:
                From the user query, extract transaction identifiers, classes, or time steps that should be looked up in the graph. Return a JSON array of filter objects.

                Filter types:
                - By tx_id: {{"filter": "tx_id", "value": "123456"}}
                - By class: {{"filter": "tx_class", "value": "illicit"}}
                - By time step: {{"filter": "time_step", "value": 5}}
                - By risk (high-risk unknown transactions): {{"filter": "high_risk"}}

                Example:
                User: "Show me illicit transactions at time step 10"
                ```json
                [{{"filter": "tx_class", "value": "illicit"}}, {{"filter": "time_step", "value": 10}}]
                ```

                User query:
                "{user_query}"

                ```json
                [Your output here]
                ```
                """
            ).strip("\n")

            self._entities_prompt = ChatPromptTemplate.from_template(tpl)

        return self._entities_prompt

    def _extract_filters(self, message: AIMessage) -> list[dict]:
        content = message.content
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            log.warning("Failed to parse filter response: {}", content)
            return []

    def _match_filters(self, filters: list[dict]) -> pd.DataFrame:
        matched_ids = set()

        for f in filters:
            filter_type = f.get("filter")

            if filter_type == "tx_id":
                node = self.ops.get_node_by_tx_id(str(f["value"]))
                if node:
                    matched_ids.add(node["node_id"])

            elif filter_type == "tx_class":
                for idx, props in self.ops._node_props.items():
                    if props.get("tx_class") == f["value"]:
                        matched_ids.add(props["node_id"])

            elif filter_type == "time_step":
                for idx, props in self.ops._node_props.items():
                    if props.get("time_step") == int(f["value"]):
                        matched_ids.add(props["node_id"])

            elif filter_type == "high_risk":
                risk_df = self.ops.high_risk_transactions(threshold=0.1)
                matched_ids.update(risk_df["node_id"].tolist())

        if not matched_ids:
            return pd.DataFrame(columns=["node_id"])

        return pd.DataFrame({"node_id": sorted(matched_ids)})

    def query_graph(
        self,
        shuffle: bool = False,
        limit: Optional[int] = None,
    ) -> RunnableFn:
        def run(inputs: dict[str, Any]) -> dict[str, Any]:
            log.info("Matching graph entities (shuffle={}, limit={})", shuffle, limit)

            filters = inputs.get("filters", [])

            try:
                entities_df = self._match_filters(filters)

                if shuffle:
                    entities_df = entities_df.sample(frac=1)

                if limit is not None:
                    entities_df = entities_df.head(limit)

                return dict(entities=entities_df)
            except Exception:
                raise GraphRetrievalException(
                    "Graph query failed", query=str(filters)
                )

        return run

    @property
    def graph_retriever(self) -> Runnable:
        if not hasattr(self, "_graph_retriever"):

            def build_prompt_inputs(inputs: dict[str, Any]) -> dict[str, str]:
                return {"user_query": inputs["user_query"]}

            def parse_filters(message: AIMessage) -> dict[str, Any]:
                return {"filters": self._extract_filters(message)}

            self._graph_retriever = (
                build_prompt_inputs
                | self.entities_prompt
                | self.code_llm
                | parse_filters
                | self.query_graph(shuffle=True, limit=100)
            )

        return self._graph_retriever

    def combined_knn(self, k: int) -> RunnableFn:
        def run(inputs: dict[str, Any]) -> dict[str, Any]:
            entities = inputs["entities"]

            if entities is None or len(entities) == 0:
                raise ContextAssemblerException("Entities not found")

            node_ids = entities.node_id.to_list()
            knn_dfs = []

            for node_id in node_ids:
                knn_df = self.ops.knn(
                    node_id,
                    max_k=k,
                    max_distance=0.25,
                    exclude=node_ids,
                )
                knn_dfs.append(knn_df)

            if not knn_dfs:
                raise ContextAssemblerException("No nearest neighbors found")

            combined = (
                pd.concat(knn_dfs)
                .groupby("node_id")
                .mean()
                .reset_index()
                .sort_values("distance")
                .head(k)["node_id"]
                .to_list()
            )

            return dict(knn=combined)

        return run

    def nn_sample_shortest_paths(
        self, n: int, min_length: int, max_length: int
    ) -> RunnableFn:
        def run(inputs: dict[str, Any]) -> dict[str, Any]:
            entities = inputs["graph_retrieval"]["entities"]

            if entities is None or len(entities) == 0:
                raise ContextAssemblerException("Entities not found")

            source_node_ids = entities.node_id.to_list()
            target_node_ids = inputs["combined_knn"]["knn"]

            if not target_node_ids:
                raise ContextAssemblerException("Nearest neighbors not found")

            paths_df = self.ops.sample_shortest_paths(
                source_node_ids, target_node_ids, n, min_length, max_length
            )

            return dict(paths=paths_df)

        return run

    def nn_random_walks(
        self, n: int, min_length: int, max_length: int
    ) -> RunnableFn:
        def run(inputs: dict[str, Any]) -> dict[str, Any]:
            source_node_ids = inputs["combined_knn"]["knn"]

            if not source_node_ids:
                raise ContextAssemblerException("Nearest neighbors not found")

            paths_dfs = [
                self.ops.random_walk(nid, n, min_length, max_length)
                for nid in source_node_ids
            ]

            return dict(paths=pd.concat(paths_dfs))

        return run

    def combine_paths(self, inputs: dict[str, Any]) -> dict[str, Any]:
        log.info("Combining paths from multiple outputs")
        dfs = [v["paths"][["paths"]] for v in inputs.values()]
        return dict(paths=pd.concat(dfs).reset_index(drop=True))

    def hydrate_paths(self, inputs: dict[str, Any]) -> dict[str, Any]:
        context = self.ops.path_descriptions(
            inputs["paths"], exclude_props=[self.column_name]
        )
        return dict(context=context)

    @property
    def context_assembler(self) -> Runnable:
        if not hasattr(self, "_context_assembler"):
            self._context_assembler = (
                RunnableParallel(
                    graph_retrieval=RunnablePassthrough(),
                    combined_knn=self.combined_knn(k=10),
                )
                | RunnableParallel(
                    nn_shortest_paths=self.nn_sample_shortest_paths(
                        n=10, min_length=1, max_length=3
                    ),
                    nn_profile_paths=self.nn_random_walks(
                        n=3, min_length=1, max_length=3
                    ),
                )
                | self.combine_paths
                | self.hydrate_paths
            )

        return self._context_assembler

    def answer_inputs_transform(self, inputs: dict[str, Any]) -> dict[str, Any]:
        user_query = inputs["user_query"]
        context = inputs["kg"]["context"]
        log.debug("Context:\n{}", context)
        return dict(user_query=user_query, context=context)

    @property
    def final_prompt(self) -> ChatPromptTemplate:
        if not hasattr(self, "_final_prompt"):
            tpl = textwrap.dedent(
                """
                You are an AI assistant analyzing Bitcoin transactions. You have access to a knowledge graph of Bitcoin payment flows from the Elliptic dataset.

                Each transaction has:
                - tx_id: unique identifier
                - tx_class: illicit, licit, or unknown
                - time_step: temporal window (1-49, ~2 weeks each)

                Relationships are payment flows: one transaction paying another.

                Use the context below to answer the user's question about transaction patterns, illicit activity, risk assessment, or payment flows.

                User query:
                "{user_query}"

                {context}

                ---

                [Your answer here]
                """
            ).strip("\n")

            self._final_prompt = ChatPromptTemplate.from_template(tpl)

        return self._final_prompt

    @property
    def answer_generator(self) -> Runnable:
        if not hasattr(self, "_answer_generator"):
            self._answer_generator = (
                self.answer_inputs_transform | self.final_prompt | self.chat_llm
            )
        return self._answer_generator

    def invoke(self, inputs, config: RunnableConfig = None) -> AIMessage:
        log.info("Running Graph RAG for:\n{}", inputs["user_query"])

        self.setup_llm_models()

        chain = (
            RunnableParallel(
                user_query=lambda inputs: inputs["user_query"],
                kg=self.graph_retriever | self.context_assembler,
            )
            | self.answer_generator
        )

        return chain.invoke(inputs, config=config)

    def loader(self, stop_event: threading.Event):
        start_time = time.time()
        symbols = ["⣾", "⣷", "⣯", "⣟", "⡿", "⢿", "⣻", "⣽"]

        while not stop_event.is_set():
            for symbol in symbols:
                elapsed = time.strftime(
                    "%H:%M:%S", time.gmtime(time.time() - start_time)
                )
                print(f"\r⏱ {elapsed} {symbol} ", end="", flush=True)
                time.sleep(0.1)

        print("\b\b\b   ", end="\n\n", flush=True)

    def interactive(self):
        config_path = user_config_path("datalab", "DataLabTechTV")
        config_path.mkdir(exist_ok=True)

        history_path = config_path / "graph_rag.history"
        session = PromptSession(history=FileHistory(history_path))

        while True:
            try:
                user_query = session.prompt(
                    ">>> ",
                    lexer=CommandLexer(),
                    placeholder=HTML("<faded>Enter a prompt (or .help)</faded>"),
                    style=Style.from_dict(
                        {"faded": "fg:#8a8a8a", "cmd": "fg:#00aeff"}
                    ),
                )
            except (KeyboardInterrupt, EOFError):
                break
            else:
                user_query = user_query.strip()

                cmd_info = [
                    f"  {cmd:<10}{info}" for cmd, info in COMMAND_INFO.items()
                ]

                match user_query:
                    case ".help":
                        print(f"Available commands:\n{chr(10).join(cmd_info)}\n")
                    case ".quit":
                        break
                    case ".clear":
                        open(history_path, "w").close()
                        session.default_buffer.history._loaded_strings.clear()
                    case _:
                        log.remove()

                        stop_event = threading.Event()
                        loader_thread = threading.Thread(
                            target=self.loader, args=(stop_event,)
                        )
                        loader_thread.start()

                        try:
                            response = self.invoke(dict(user_query=user_query))
                            stop_event.set()
                            loader_thread.join()
                            print(response.content)
                        except GraphRetrievalException as e:
                            stop_event.set()
                            loader_thread.join()
                            print(Fore.RED + "Error: " + str(e))
                            print(Fore.MAGENTA + e.query + Fore.RESET)
                        except ContextAssemblerException as e:
                            stop_event.set()
                            loader_thread.join()
                            print(Fore.RED + "Error: " + str(e) + Fore.RESET)
