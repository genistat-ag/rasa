import logging
import json
import os
from typing import Any, List, Text, Dict, Optional

import rasa.utils.io

from rasa.core import utils
from rasa.core.actions.action import (
    ACTION_BACK_NAME,
    ACTION_LISTEN_NAME,
    ACTION_RESTART_NAME,
)
from rasa.core.constants import USER_INTENT_BACK, USER_INTENT_RESTART
from rasa.core.domain import Domain
from rasa.core.events import ActionExecuted
from rasa.core.policies.policy import Policy
from rasa.core.trackers import DialogueStateTracker

logger = logging.getLogger(__name__)


class MappingPolicy(Policy):
    """Policy which maps intents directly to actions.

    Intents can be assigned actions in the domain file which are to be
    executed whenever the intent is detected. This policy takes precedence over
    any other policy."""

    defaults = {"priority": 3}

    def __init__(
        self,
        config: Optional[Dict[Text, Any]] = None,
        featurizer: Optional = None,
        **kwargs: Any
    ) -> None:
        """Create a new Mapping policy."""

        if config is None:
            config = {}
        config.update(kwargs)

        super(MappingPolicy, self).__init__(config)

    def train(
        self,
        training_trackers: List[DialogueStateTracker],
        domain: Domain,
        **kwargs: Any
    ) -> None:
        """Does nothing. This policy is deterministic."""

        pass

    def predict_action_probabilities(
        self, tracker: DialogueStateTracker, domain: Domain
    ) -> List[float]:
        """Predicts the assigned action.

        If the current intent is assigned to an action that action will be
        predicted with the highest probability of all policies. If it is not
        the policy will predict zero for every action."""

        prediction = [0.0] * domain.num_actions
        intent = tracker.latest_message.intent.get("name")
        action = domain.intent_properties.get(intent, {}).get("triggers")
        if tracker.latest_action_name == ACTION_LISTEN_NAME:
            if action:
                idx = domain.index_for_action(action)
                if idx is None:
                    logger.warning(
                        "MappingPolicy tried to predict unkown "
                        "action '{}'.".format(action)
                    )
                else:
                    prediction[idx] = 1
            elif intent == USER_INTENT_RESTART:
                idx = domain.index_for_action(ACTION_RESTART_NAME)
                prediction[idx] = 1
            elif intent == USER_INTENT_BACK:
                idx = domain.index_for_action(ACTION_BACK_NAME)
                prediction[idx] = 1

            if any(prediction):
                logger.debug(
                    "The predicted intent '{}' is mapped to "
                    " action '{}' in the domain."
                    "".format(intent, action)
                )
        elif tracker.latest_action_name == action and action is not None:
            latest_action = tracker.get_last_event_for(ActionExecuted)
            assert latest_action.action_name == action

            if latest_action.policy == type(self).__name__:
                # this ensures that we only predict listen, if we predicted
                # the mapped action
                logger.debug(
                    "The mapped action, '{}', for this intent, '{}', was "
                    "executed last so MappingPolicy is returning to "
                    "action_listen.".format(action, intent)
                )

                idx = domain.index_for_action(ACTION_LISTEN_NAME)
                prediction[idx] = 1
        else:
            logger.debug(
                "There is no mapped action for the predicted intent, "
                "'{}'.".format(intent)
            )
        return prediction

    def persist(self, path: Text) -> None:
        """Only persists the priority."""

        config_file = os.path.join(path, "mapping_policy.json")
        rasa.utils.io.create_directory_for_file(config_file)
        utils.dump_obj_as_json_to_file(config_file, self.config)

    @classmethod
    def load(cls, path: Text) -> "MappingPolicy":
        """Returns the class with the configured priority."""

        meta = {}
        if os.path.exists(path):
            meta_path = os.path.join(path, "mapping_policy.json")
            if os.path.isfile(meta_path):
                meta = json.loads(rasa.utils.io.read_file(meta_path))

        return cls(**meta)
