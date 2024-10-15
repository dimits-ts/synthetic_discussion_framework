from sdl import actors
from sdl import util
from sdl import models
from sdl import conversation

import dataclasses
import json


@dataclasses.dataclass
class LLMConvData:
    """
    A dataclass responsible for serializing and deserializing data needed to construct a :class:`Conversation`.
    """
    context: str
    user_names: list[str]
    user_attributes: list[list[str]]
    user_instructions: str
    conv_len: int = 4
    history_ctx_len: int = 4
    moderator_name: str | None = None
    moderator_attributes: list[str] | None = None
    moderator_instructions: str | None = None

    def __post_init__(self):
        assert len(self.user_names) == len(
            self.user_attributes
        ), "Number of actor names and actor attribute lists must be the same"

    @staticmethod
    def from_json_file(input_file_path: str):
        """
        Construct a LLMConvData instance according to a serialized .json file.

        :param input_file_path: The path to the serialized .json file
        :type input_file_path: str
        :return: A LLMConvData instance containing the information from the file
        :rtype: LLMConvData
        """
        with open(input_file_path, "r", encoding="utf8") as fin:
            data_dict = json.load(fin)

        # code from https://stackoverflow.com/questions/68417319/initialize-python-dataclass-from-dictionary
        field_set = {f.name for f in dataclasses.fields(LLMConvData) if f.init}
        filtered_arg_dict = {k: v for k, v in data_dict.items() if k in field_set}
        return LLMConvData(**filtered_arg_dict)

    def to_json_file(self, output_path: str) -> None:
        """
        Serialize the data to a .json file.

        :param output_path: The path of the new file
        :type output_path: str
        """
        with open(output_path, "w", encoding="utf8") as fout:
            json.dump(dataclasses.asdict(self), fout, indent=4)


class LLMConvGenerator:
    """
    A class responsible for creating a :class:`Conversation` from the conversation data (:class:`LLMConvData`)
    and a model (:class:`models.LlamaModel`).
    """

    def __init__(self,
                 data: LLMConvData,
                 user_model: models.LlamaModel,
                 moderator_model: models.LlamaModel | None,
                 ):
        """
        Initialize the generator.

        :param data: The deserialized conversation input data
        :type data: LLMConvData
        :param user_model: The model used for the users to talk
        :type user_model: tasks.models.LlamaModel
        :param moderator_model: The model used for the moderator to talk, if he exists
        :type moderator_model: tasks.models.LlamaModel | None
        """
        assert user_model is not None, "User model cannot be None"
        assert not (moderator_model is None and data.moderator_name is not None), ("Moderator agent was not given a "
                                                                                   "model.")
        self.user_model = user_model
        self.moderator_model = moderator_model
        self.data = data

    def produce_conversation(self) -> conversation.Conversation:
        """
        Generate a conversation.

        :return: An initialized Conversation instance.
        :rtype: Conversation
        """
        user_list = []

        for i in range(len(self.data.user_names)):
            user_list.append(actors.LLMUser(model=self.user_model,
                                                name=self.data.user_names[i],
                                                role="chat user",
                                                attributes=self.data.user_attributes[i],
                                                context=self.data.context,
                                                instructions=self.data.user_instructions))
        if self.data.moderator_name is not None:
            moderator = actors.LLMUser(model=self.moderator_model,
                                           name=self.data.moderator_name,
                                           role="chat moderator",
                                           attributes=self.data.moderator_attributes,
                                           context=self.data.context,
                                           instructions=self.data.moderator_instructions)
        else:
            moderator = None

        generated_conv = conversation.Conversation(users=user_list,
                                    moderator=moderator,
                                    history_context_len=self.data.history_ctx_len,
                                    conv_len=self.data.conv_len)
        return generated_conv