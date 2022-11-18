from pathlib import Path
import json

from .._services.model_repository import ModelRepository as mr


def find_file(model, fileName):
    """
    Retrieves first file from specified model that contains fileName as a substring.
    Parameters
    ----------
    model : str
        ID of the model the desired file is located in
    fileName : str
        The name of the desired file, or a substring that is contained within the file name
    Returns
    -------
    RestObj
        The first file with a name containing fileName

    """
    from ..core import current_session

    sess = current_session()
    fileList = mr.get_model_contents(model)
    for file in fileList:
        print(file.name)
        if fileName.lower() in file.name.lower():
            correctFile = sess.get(
                "modelRepository/models/{}/contents/{}/content".format(model, file.id)
            )
            break
    return correctFile


class ModelParameters:
    @classmethod
    def generate_hyperparameters(cls, model, modelPrefix, pPath):
        """
        Generates hyperparameters for a given model
        Parameters
        ----------
        model : str, list, dict
            Name, id, or dictionary representation of the model
        modelPrefix : str
            Name used to create model files
            e.g. (modelPrefix) + "Hyperparameters.json")
        pPath : str, Path
            Directory location of model files
        """
        if all(hasattr(model, attr) for attr in ["_estimator_type", "get_params"]):
            cls.sklearn_params(model, modelPrefix, pPath)
        else:
            print(
                "Other model types not currently supported for hyperparameter generation."
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
        project : dict, str, list
            Name, id, or dictionary representation of the project
        server : str, optional
            Server on which the KPI data table is stored. Defaults to "cas-shared-default".
        caslib : str, optional
            CAS Library on which the KPI data table is stored. Defaults to "ModelPerformanceData".
        """
        from ..tasks import get_project_kpis
        from io import StringIO

        kpis = get_project_kpis(project, server, caslib)
        modelsToUpdate = kpis["ModelUUID"].unique().tolist()
        for model in modelsToUpdate:
            currentParams = find_file(model, "hyperparameters")
            currentJSON = currentParams.json()
            modelRows = kpis.loc[kpis["ModelUUID"] == model]
            modelRows.set_index("TimeLabel", inplace=True)
            kpiJSON = modelRows.to_json(orient="index")
            parsedJSON = json.loads(kpiJSON)
            currentJSON["kpis"] = parsedJSON
            fileName = "{}Hyperparameters.json".format(
                currentJSON["kpis"][list(currentJSON["kpis"].keys())[0]]["ModelName"]
            )
            mr.add_model_content(
                model,
                StringIO((json.dumps(currentJSON, indent=4))),
                fileName,
            )

    @classmethod
    def get_hyperparameters(cls, model):
        """
        Gets hyperparameter json file from specified model.
        Parameters
        ----------
        model : str, dict, list
            Name, id, or dictionary representation of the model
        Returns
        -------
        dict
            dictionary containing the contents of the hyperparameter file
        """
        if mr.is_uuid(model):
            id_ = model
        elif isinstance(model, dict) and "id" in model:
            id_ = model["id"]
        else:
            model = mr.get_model(model)
            id_ = model["id"]
        file = find_file(id_, "hyperparameters")
        return file.json()

    @classmethod
    def add_hyperparameters(cls, model, **kwargs):
        """
        Adds custom hyperparameters to the hyperparameter file contained within the model in Model Manager.
        Parameters
        ----------
        model : str, dict
            name, id, or dictionary representation of the model
        kwargs
            named variables representing hyperparameters to be added to the hyperparameter file
        """
        from io import StringIO

        if not isinstance(model, dict):
            model = mr.get_model(model)
        hyperparameters = cls.get_hyperparameters(model.id)
        for key, value in kwargs.items():
            hyperparameters["hyperparameters"][key] = value
        mr.add_model_content(
            model,
            StringIO((json.dumps(hyperparameters, indent=4))),
            "{}Hyperparameters.json".format(model.name),
        )

    def sklearn_params(model, modelPrefix, pPath):
        """
        Generates hyperparameters for the models genereated by SciKit Learn.
        Parameters
        ----------
        modelPrefix : str
            Name used to create model files
        pPath : str, Path
            Directory location of model files
        """
        hyperparameters = model.get_params()
        modelJson = {"hyperparameters": hyperparameters}
        with open(
            Path(pPath) / ("{}Hyperparameters.json".format(modelPrefix)), "w"
        ) as f:
            f.write(json.dumps(modelJson, indent=4))
