#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2023, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
import tempfile
from pathlib import Path

import pandas as pd

from sasctl.pzmm.write_json_files import JSONFiles as jf

# Example input variable list from hmeq dataset (generated by mlflow_model.py)
input_dict = [
    {"name": "LOAN", "type": "long"},
    {"name": "MORTDUE", "type": "double"},
    {"name": "VALUE", "type": "double"},
    {"name": "YOJ", "type": "double"},
    {"name": "DEROG", "type": "double"},
    {"name": "DELINQ", "type": "double"},
    {"name": "CLAGE", "type": "double"},
    {"name": "NINQ", "type": "double"},
    {"name": "CLNO", "type": "double"},
    {"name": "DEBTINC", "type": "double"},
    {"name": "JOB_Office", "type": "integer"},
    {"name": "JOB_Other", "type": "integer"},
    {"name": "JOB_ProfExe", "type": "integer"},
    {"name": "JOB_Sales", "type": "integer"},
    {"name": "JOB_Self", "type": "integer"},
    {"name": "REASON_HomeImp", "type": "integer"},
]


def test_generate_variable_properties(hmeq_dataset):
    """
    Test cases:
    - Return expected variable properties from hmeq dataset
    """
    df = hmeq_dataset
    # Generate the variable properties from the dataset (excluding the target variable)
    dict_list = jf.generate_variable_properties(df.drop(["BAD"], axis=1))
    # Find all expected variables
    assert len(dict_list) == 12
    # Verify expected variable properties
    for var in dict_list:
        if var["name"] in ["REASON", "JOB"]:
            assert var["level"] == "nominal" and var["type"] == "string"
        else:
            assert var["level"] == "interval" and var["type"] == "decimal"


def test_generate_mlflow_variable_properties():
    """
    Test cases:
    - Return expected number of variables from mlflow_model.py output
    """
    dict_list = jf.generate_mlflow_variable_properties(input_dict)
    assert len(dict_list) == 16


def test_write_var_json(hmeq_dataset):
    """
    Test cases:
    - Generate correctly named file based on is_input (assuming path provided)
    - Return correctly labelled dict based on is_input (assuming no path provided)
    - Return correctly labelled dict from Mlflow model dataset
    """
    df = hmeq_dataset
    with tempfile.TemporaryDirectory() as tmp_dir:
        jf.write_var_json(df, True, Path(tmp_dir))
        assert (Path(tmp_dir) / "inputVar.json").exists()

    var_dict = jf.write_var_json(df, False)
    assert "outputVar.json" in var_dict

    var_mlflow_dict = jf.write_var_json(input_dict, True)
    assert "inputVar.json" in var_mlflow_dict


def test_write_model_properties_json():
    """
    Test Cases:
    - Generate correctly named file with json_path generated
    - Return correctly labelled dict when no json_path is provided
    - Truncate model description that is too long
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        jf.write_model_properties_json(
            model_name="Test_Model",
            target_variable="BAD",
            target_event="1",
            num_target_categories=2,
            json_path=Path(tmp_dir)
        )
        assert (Path(tmp_dir) / "ModelProperties.json").exists()

    prop_dict = jf.write_model_properties_json(
        model_name="Test_Model",
        target_variable="BAD",
        target_event="1",
        num_target_categories=2,
    )
    assert "ModelProperties.json" in prop_dict

    prop_dict = jf.write_model_properties_json(
        model_name="Test_Model",
        target_variable="BAD",
        target_event="1",
        num_target_categories=2,
        model_desc="a" * 2000
    )
    assert len(json.loads(prop_dict["ModelProperties.json"])["description"]) <= 1024
