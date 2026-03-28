{{ config(alias='transactions') }}

WITH features_numbered AS (
    SELECT row_number() OVER () AS row_num, *
    FROM {{ ref('ebtc_txs_features') }}
),

classes_numbered AS (
    SELECT row_number() OVER () AS row_num, *
    FROM {{ ref('ebtc_txs_classes') }}
)

SELECT
    c.tx_id,
    c.tx_class,
    f.time_step,
    f.lf_1, f.lf_2, f.lf_3, f.lf_4, f.lf_5, f.lf_6, f.lf_7, f.lf_8, f.lf_9, f.lf_10,
    f.lf_11, f.lf_12, f.lf_13, f.lf_14, f.lf_15, f.lf_16, f.lf_17, f.lf_18, f.lf_19, f.lf_20,
    f.lf_21, f.lf_22, f.lf_23, f.lf_24, f.lf_25, f.lf_26, f.lf_27, f.lf_28, f.lf_29, f.lf_30,
    f.lf_31, f.lf_32, f.lf_33, f.lf_34, f.lf_35, f.lf_36, f.lf_37, f.lf_38, f.lf_39, f.lf_40,
    f.lf_41, f.lf_42, f.lf_43, f.lf_44, f.lf_45, f.lf_46, f.lf_47, f.lf_48, f.lf_49, f.lf_50,
    f.lf_51, f.lf_52, f.lf_53, f.lf_54, f.lf_55, f.lf_56, f.lf_57, f.lf_58, f.lf_59, f.lf_60,
    f.lf_61, f.lf_62, f.lf_63, f.lf_64, f.lf_65, f.lf_66, f.lf_67, f.lf_68, f.lf_69, f.lf_70,
    f.lf_71, f.lf_72, f.lf_73, f.lf_74, f.lf_75, f.lf_76, f.lf_77, f.lf_78, f.lf_79, f.lf_80,
    f.lf_81, f.lf_82, f.lf_83, f.lf_84, f.lf_85, f.lf_86, f.lf_87, f.lf_88, f.lf_89, f.lf_90,
    f.lf_91, f.lf_92, f.lf_93,
    f.af_1, f.af_2, f.af_3, f.af_4, f.af_5, f.af_6, f.af_7, f.af_8, f.af_9, f.af_10,
    f.af_11, f.af_12, f.af_13, f.af_14, f.af_15, f.af_16, f.af_17, f.af_18, f.af_19, f.af_20,
    f.af_21, f.af_22, f.af_23, f.af_24, f.af_25, f.af_26, f.af_27, f.af_28, f.af_29, f.af_30,
    f.af_31, f.af_32, f.af_33, f.af_34, f.af_35, f.af_36, f.af_37, f.af_38, f.af_39, f.af_40,
    f.af_41, f.af_42, f.af_43, f.af_44, f.af_45, f.af_46, f.af_47, f.af_48, f.af_49, f.af_50,
    f.af_51, f.af_52, f.af_53, f.af_54, f.af_55, f.af_56, f.af_57, f.af_58, f.af_59, f.af_60,
    f.af_61, f.af_62, f.af_63, f.af_64, f.af_65, f.af_66, f.af_67, f.af_68, f.af_69, f.af_70,
    f.af_71, f.af_72
FROM features_numbered AS f
LEFT JOIN classes_numbered AS c
    ON f.row_num = c.row_num
