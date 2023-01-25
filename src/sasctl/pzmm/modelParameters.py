# Copyright (c) 2022, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from distutils.version import StrictVersion
from io import StringIO

import pandas as pd
from pathlib import Path

from .._services.model_repository import ModelRepository as mr
from ..core import current_session, is_uuid

# TODO: Convert STRINGIO calls to string or dict format


def _find_file(model, file_name):
    """
    Retrieves the first file from a registered model on SAS Model Manager that contains the provided
    file_name as an exact match or substring.

    Parameters
    ----------
    model : str or dict
        The name or id of the model, or a dictionary representation of the model.
    file_name : str
        The name of the desired file, or a substring that is contained within the file name.

    Returns
    -------
    RestObj
        The first file with a name containing file_name.
    """

    sess = current_session()
    file_list = mr.get_model_contents(model)
    for file in file_list:
        print(file.name)
        if file_name.lower() in file.name.lower():
            correct_file = sess.get(
                f"modelRepository/models/{model}/contents/{file.id}/content"
            )
            return correct_file


class ModelParameters:
    @classmethod
    def generate_hyperparameters(cls, model, model_prefix, pickle_path):
        """
        Generates hyperparameters for a given model and creates a JSON file representation.

        Currently only supports generation of scikit-learn model hyperparameters.

        Parameters
        ----------
        model : Python object
            Python object representing the model.
        model_prefix : str
            Name used to create model files. (e.g. (modelPrefix) + "Hyperparameters.json")
        pickle_path : str, Path
            Directory location of model files.

        Yields
        ------
        JSON file
            Named {model_prefix}Hyperparameters.json.
        """

        def sklearn_params():
            """
            Generates hyperparameters for the models generated by scikit-learn.
            """
            hyperparameters = model.get_params()
            model_json = {"hyperparameters": hyperparameters}
            with open(
                Path(pickle_path) / f"{model_prefix}Hyperparameters.json", "w"
            ) as f:
                f.write(json.dumps(model_json, indent=4))

        if all(hasattr(model, attr) for attr in ["_estimator_type", "get_params"]):
            sklearn_params()
        else:
            raise ValueError(
                "This model type is not currently supported for hyperparameter generation."
            )

    @classmethod
    def update_kpis(
        cls,
        project,
        server="cas-shared-default",
        caslib="ModelPerformanceData",
    ):
        """
        Updates hyperparameter file to include KPIs generated by performance definitions, as well
        as any custom KPIs imported by user to the SAS KPI data table.

        Parameters
        ----------
        project : str or dict
            The name or id of the project, or a dictionary representation of the project.
        server : str, optional
            Server on which the KPI data table is stored. Defaults to "cas-shared-default".
        caslib : str, optional
            CAS Library on which the KPI data table is stored. Defaults to "ModelPerformanceData".
        """
        kpis = cls.get_project_kpis(project, server, caslib)
        models_to_update = kpis["ModelUUID"].unique().tolist()
        for model in models_to_update:
            current_params = _find_file(model, "hyperparameters")
            current_json = current_params.json()
            model_rows = kpis.loc[kpis["ModelUUID"] == model]
            model_rows.set_index("TimeLabel", inplace=True)
            kpi_json = model_rows.to_json(orient="index")
            parsed_json = json.loads(kpi_json)
            current_json["kpis"] = parsed_json
            file_name = "{}Hyperparameters.json".format(
                current_json["kpis"][list(current_json["kpis"].keys())[0]]["ModelName"]
            )
            mr.add_model_content(
                model,
                StringIO(json.dumps(current_json, indent=4)),
                file_name,
            )

    @classmethod
    def get_hyperparameters(cls, model):
        """
        Retrieves the hyperparameter json file from specified model on SAS Model Manager.

        Parameters
        ----------
        model : str or dict
            The name or id of the model, or a dictionary representation of the model.

        Returns
        -------
        dict
            Dictionary containing the contents of the hyperparameter file.
        """
        if mr.is_uuid(model):
            id_ = model
        elif isinstance(model, dict) and "id" in model:
            id_ = model["id"]
        else:
            model = mr.get_model(model)
            id_ = model["id"]
        file = _find_file(id_, "hyperparameters")
        return file.json()

    @classmethod
    def add_hyperparameters(cls, model, **kwargs):
        """
        Adds custom hyperparameters to the hyperparameter file contained within the model in SAS Model Manager.

        Parameters
        ----------
        model : str or dict
            The name or id of the model, or a dictionary representation of the model.
        kwargs
            Named variables pairs representing hyperparameters to be added to the hyperparameter file.
        """

        if not isinstance(model, dict):
            model = mr.get_model(model)
        hyperparameters = cls.get_hyperparameters(model.id)
        for key, value in kwargs.items():
            hyperparameters["hyperparameters"][key] = value
        mr.add_model_content(
            model,
            StringIO(json.dumps(hyperparameters, indent=4)),
            f"{model.name}Hyperparameters.json",
        )

    @staticmethod
    def get_project_kpis(
        project,
        server="cas-shared-default",
        caslib="ModelPerformanceData",
        filter_column=None,
        filter_value=None,
    ):
        """Create a call to CAS to return the MM_STD_KPI table (SAS Model Manager
        Standard KPI) generated when custom KPIs are uploaded or when a performance
        definition is executed on SAS Model Manager on SAS Viya 4.

        Filtering options are available as additional arguments. The filtering is based
        on column name and column value. Currently, only exact matches are available
        when filtering by this method.

        Parameters
        ----------
        project : str or dict
            The name or id of the project, or a dictionary representation of the
            project.
        server : str, optional
            SAS Viya 4 server where the MM_STD_KPI table exists, by default
            "cas-shared-default".
        caslib : str, optional
            SAS Viya 4 caslib where the MM_STD_KPI table exists, by default
            "ModelPerformanceData".
        filter_column : str, optional
            Column name from the MM_STD_KPI table to be filtered, by default None.
        filter_value : str, optional
            Column value to be filtered, by default None.

        Returns
        -------
        kpi_table_df : pandas DataFrame
            A pandas DataFrame representing the MM_STD_KPI table. Note that SAS
            missing values are replaced with pandas valid missing values.
        """
        # Check the pandas version for where the json_normalize function exists
        if pd.__version__ >= StrictVersion("1.0.3"):
            from pandas import json_normalize
        else:
            from pandas.io.json import json_normalize

        # Collect the current session for authentication of API calls
        sess = current_session()

        # Step through options to determine project UUID
        if is_uuid(project):
            project_id = project
        elif isinstance(project, dict) and "id" in project:
            project_id = project["id"]
        else:
            project = mr.get_project(project)
            project_id = project["id"]

        # TODO: include case for large MM_STD_KPI tables
        # Call the casManagement service to collect the column names in the table
        kpi_table_columns = sess.get(
            "casManagement/servers/{}/".format(server)
            + "caslibs/{}/tables/".format(caslib)
            + "{}.MM_STD_KPI/columns?limit=10000".format(project_id)
        )
        if not kpi_table_columns:
            project = mr.get_project(project)
            raise SystemError(
                "No KPI table exists for project {}.".format(project.name)
                + " Please confirm that the performance definition completed"
                + " or custom KPIs have been uploaded successfully."
            )
        # Parse through the json response to create a pandas DataFrame
        cols = json_normalize(kpi_table_columns.json(), "items")
        # Convert the columns to a readable list
        col_names = cols["name"].to_list()

        # Filter rows returned by column and value provided in arguments
        where_statement = ""
        if filter_column and filter_value:
            where_statement = "&where={}='{}'".format(filter_column, filter_value)

        # Call the casRowSets service to return row values
        # Optional where statement is included
        kpi_table_rows = sess.get(
            "casRowSets/servers/{}/".format(server)
            + "caslibs/{}/tables/".format(caslib)
            + "{}.MM_STD_KPI/rows?limit=10000".format(project_id)
            + "{}".format(where_statement)
        )
        # If no "cells" are found in the json response, return an error
        try:
            kpi_table_df = pd.DataFrame(
                json_normalize(kpi_table_rows.json()["items"])["cells"].to_list(),
                columns=col_names,
            )
        except KeyError:
            if filter_column and filter_value:
                raise SystemError(
                    "No KPIs were found when filtering with {}='{}'.".format(
                        filter_column, filter_value
                    )
                )
            else:
                project_name = mr.get_project(project)["name"]
                raise SystemError("No KPIs were found for project {}.".format(project_name))

        # Strip leading spaces from cells of KPI table; convert missing values to None
        kpi_table_df = kpi_table_df.apply(lambda x: x.str.strip())\
            .replace([".", ""], None)

        return kpi_table_df

