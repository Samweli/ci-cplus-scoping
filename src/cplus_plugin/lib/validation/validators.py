"""
Aggregated and individual rule validators.
"""

import traceback
import typing

from qgis.PyQt import QtCore

from qgis.core import QgsRasterLayer, QgsTask


from ...models.base import LayerModelComponent, NcsPathway
from ...models.validation import (
    RuleConfiguration,
    RuleResult,
    RuleType,
    ValidationCategory,
    ValidationResult,
)
from ...utils import log, tr


class BaseRuleValidator:
    """Validator for an individual rule.

    This is an abstract class that needs to be subclassed with the
    specific validation implementation by overriding the `validate`
    protected function.
    """

    def __init__(self, configuration: RuleConfiguration):
        self._config = configuration
        self._result: RuleResult = None
        self.model_components: typing.List[LayerModelComponent] = list()

    @property
    def rule_configuration(self) -> RuleConfiguration:
        """Returns the rule configuration use in the validator.

        :returns: Rule configuration used in the validator.
        :rtype: RuleConfiguration
        """
        return self._config

    @property
    def result(self) -> RuleResult:
        """Returns the result of the validation process.

        :returns: Result of the validation process.
        :rtype: RuleResult
        """
        return self._result

    @property
    def rule_type(self) -> RuleType:
        """Returns the type identified of the rule validator.

        :returns: Type identified of the rule validator.
        :rtype: RuleType
        """
        raise NotImplementedError

    def _validate(self) -> bool:
        """Initiates the validation process.

        Subclasses need to override this method with the specific
        validation implementation and set the 'result' attribute
        value.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        raise NotImplementedError

    def log(self, message: str, info: bool = True):
        """Convenience function that logs the given messages by appending
        the information in the rule configuration.

        :param message: Message to be logged.
        :type message: str

        :param info: False if the message should be logged as a warning
        else True if information.
        :type info: bool
        """
        msg = f"{self._config.rule_name} - {message}"
        log(message=msg, info=info)

    def run(self) -> bool:
        """Initiates the rule validation process and returns
        a result indicating whether the process succeeded or
        failed.

        A fail result would, for instance, be due to no layers,
        or only one layer, defined for validation.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        if len(self.model_components) < 2:
            msg = tr("At least two layers are required for the validation process.")
            self.log(msg, False)

            return False

        return self._validate()


BaseRuleValidatorType = typing.TypeVar("BaseRuleValidatorType", bound=BaseRuleValidator)


class RasterValidator(BaseRuleValidator):
    """Checks if the input datasets are raster layers."""

    def _validate(self) -> bool:
        """Checks whether all input datasets are raster layers.

        If a layer is not valid, it will also be included in the list
        of non-raster datasets.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True
        non_raster_model_components = []

        for model_component in self.model_components:
            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False
                non_raster_model_components.append(model_component.name)
            else:
                layer = model_component.to_map_layer()
                if not isinstance(layer, QgsRasterLayer):
                    non_raster_model_components.append(model_component.name)

        summary = ""
        validate_info = []
        if not status:
            summary = tr("There are invalid non-raster datasets")
            invalid_layer_names = ", ".join(non_raster_model_components)
            validate_info = [(tr("Non-raster datasets"), invalid_layer_names)]

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        return status

    def rule_type(self) -> RuleType:
        """Returns the raster type rule validator.

        :returns: Raster type rule validator.
        :rtype: RuleType
        """
        return RuleType.DATA_TYPE


class DataValidator(QgsTask):
    """Runner for checking a set of datasets against specific validation
    rules.

    Rule validators need to be added manually in this default implementation.
    """

    NAME = "Default Data Validator"

    rule_validation_finished = QtCore.pyqtSignal(RuleResult)
    validation_completed = QtCore.pyqtSignal()

    def __init__(self, model_components=None):
        super().__init__(tr(self.NAME))

        self.model_components = []
        if model_components is not None:
            self.model_components = model_components

        self._result: ValidationResult = None
        self._rule_validators = []
        self._rule_results = []

    def _validate(self) -> bool:
        """Initiates the validation process based on the specified
        rule validators.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        for rule_validator in self._rule_validators:
            rule_validator.model_components = self.model_components
            rule_validator.run()
            if rule_validator.result is not None:
                self.rule_validation_finished.emit(rule_validator.result)

    def log(self, message: str, info: bool = True):
        """Convenience function that logs the given messages by appending
        the information for the validator.

        :param message: Message to be logged.
        :type message: str

        :param info: False if the message should be logged as a warning
        else True if information.
        :type info: bool
        """
        msg = f"{self.NAME} - {message}"
        log(message=msg, info=info)

    def cancel(self):
        """Cancel the validation process."""
        self.log(tr("Validation process has been cancelled."))

        super().cancel()

    def run(self) -> bool:
        """Initiates the validation process based on the
        specified validators and returns a result indicating
        whether the process succeeded or failed.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        if len(self._rule_validators) == 0:
            msg = tr("No rule validators specified.")
            self.log(msg, False)

            return False

        if len(self.model_components) < 2:
            msg = tr("At least two datasets are required for the validation process.")
            self.log(msg, False)

            return False

        status = True

        try:
            self._validate()
        except Exception as ex:
            exc_info = "".join(traceback.TracebackException.from_exception(ex).format())
            self.log(exc_info, False)
            status = False

        return status

    @staticmethod
    def rule_validators() -> dict[RuleType, typing.Type[BaseRuleValidator]]:
        """Returns all the rule validator classes, any new validator
        type needs to be added here.

        The validator classes are indexed by their corresponding rule
        type enum.

        :returns: Collection containing rule validator classes indexed
        by their corresponding rule types.
        :rtype: dict
        """
        return {RuleType.DATA_TYPE: RasterValidator}

    @staticmethod
    def validator_cls_by_type(rule_type: RuleType) -> typing.Type[BaseRuleValidator]:
        """Gets the rule validator class based on the corresponding rule type.

        :param rule_type: The type of the validator rule.
        :type rule_type: RuleType

        :returns: The rule validator class corresponding to the
        given rule type.
        :rtype: BaseRuleValidator
        """
        return DataValidator.rule_validators()[rule_type]

    @staticmethod
    def create_rule_validator(
        rule_type: RuleType, config: RuleConfiguration
    ) -> BaseRuleValidator:
        """Factory method for creating a rule validator object.

        :param rule_type: The type of the validator rule.
        :type rule_type: RuleType

        :param config: The context information for configuring
        the rule validator.
        :type rule_type: RuleConfiguration

        :returns: An instance of the specific rule validator.
        :rtype: BaseRuleValidator
        """
        validator_cls = DataValidator.validator_cls_by_type(rule_type)

        return validator_cls(config)

    def add_rule_validator(self, rule_validator: BaseRuleValidator):
        """Add a rule validator for validating the input model components.

        :param rule_validator: Validator for checking the input model
        components based on the specific validation rule.
        :type rule_validator: BaseRuleValidator
        """
        self._rule_validators.append(rule_validator)

    def finished(self, result: bool):
        """Depending on the outcome of the validation process,
        `validation_completed` signal will be emitted only if the
        validation was successful. The `result` attribute will also contain the
        validation result object. If an error occurred during the validation
        process, the validation result object will be None.

        :param result: True if the validation process was successful, else False.
        :type result: bool
        """
        if result:
            rule_results = [
                rule_validator.result for rule_validator in self._rule_validators
            ]
            self._result = ValidationResult(rule_results)
            self.validation_completed.emit()
