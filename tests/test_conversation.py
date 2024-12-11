import unittest
from unittest.mock import MagicMock, patch
import tempfile

import json

from ..src.sdl.backend.actors import LLMUser
from ..src.sdl.backend.cpp_model import LlamaModel
from ..src.sdl.generation.conversation import Conversation
from ..src.sdl.backend import turn_manager
from ..src.sdl.util import output_util
from ..src.sdl.serialization.conversation_io import LLMConvData, LLMConvGenerator


class TestLLMConvData(unittest.TestCase):
    # mostly generated by LLM
    # TODO: add more edge cases

    def test_constructor_assertions(self):
        # Test invalid cases with mismatched user names and attributes
        with self.assertRaises(AssertionError):
            LLMConvData(
                context="Test context",
                user_names=["Steve2001", "GeorgeBush78"],
                user_attributes=[["African American"]],
                user_instructions="Sample instructions",
                turn_manager_type="round robin"
            )
        
        # Test valid case where user names and attributes are matched
        data = LLMConvData(
            context="Sample context",
            user_names=["User1", "User2"],
            user_attributes=[["Attribute1"], ["Attribute2"]],
            user_instructions="Sample user instructions",
            turn_manager_type="round robin"
        )
        self.assertEqual(len(data.user_names), len(data.user_attributes))

    def test_optional_fields(self):
        # Test creation with and without optional fields
        data_with_moderator = LLMConvData(
            context="Sample context",
            user_names=["User1", "User2"],
            user_attributes=[["Attribute1"], ["Attribute2"]],
            user_instructions="User instructions",
            turn_manager_type="round robin",
            moderator_name="Moderator1",
            moderator_attributes=["Firm", "Calm"],
            moderator_instructions="Sample moderator instructions"
        )
        self.assertIsNotNone(data_with_moderator.moderator_name)
        self.assertIsNotNone(data_with_moderator.moderator_attributes)
        
        # Case without optional fields
        data_without_moderator = LLMConvData(
            context="Sample context",
            user_names=["User1", "User2"],
            user_attributes=[["Attribute1"], ["Attribute2"]],
            user_instructions="User instructions",
            turn_manager_type="round robin"
        )
        self.assertIsNone(data_without_moderator.moderator_name)
        self.assertIsNone(data_without_moderator.moderator_attributes)

    def test_from_json_file(self):
        temp = tempfile.NamedTemporaryFile()

        # Create a sample JSON file to test deserialization
        sample_data = {
            "context": "Test context",
            "user_names": ["User1", "User2"],
            "user_attributes": [["Attr1"], ["Attr2"]],
            "user_instructions": "Test instructions",
            "turn_manager_type": "round robin"
        }
        with open(temp.name, "w") as f:
            json.dump(sample_data, f)

        # Test loading the JSON file
        data = LLMConvData.from_json_file(temp.name)
        self.assertEqual(data.context, sample_data["context"])
        self.assertEqual(data.user_names, sample_data["user_names"])

    def test_json_file(self):
        temp = tempfile.NamedTemporaryFile()

        # Create an LLMConvData instance and serialize it
        data = LLMConvData(
            context="Test context for serialization",
            user_names=["User1", "User2"],
            user_attributes=[["Attr1"], ["Attr2"]],
            user_instructions="User instructions",
            turn_manager_type="round robin"
        )
        data.to_json_file(temp.name)

        # Reload the JSON file and check the content
        with open(temp.name, "r") as f:
            loaded_data = json.load(f)
        self.assertEqual(loaded_data["context"], data.context)
        self.assertEqual(loaded_data["user_names"], data.user_names)

        # Test loading the JSON file
        read_data = LLMConvData.from_json_file(temp.name)
        self.assertEqual(data.context, read_data.context)
        self.assertEqual(data.user_names, read_data.user_names)


    def test_invalid_json_structure(self):
        # Create an invalid JSON file to test error handling
        temp = tempfile.NamedTemporaryFile(mode='w+t')
        with open(temp.name, "w") as f:
            f.write("{invalid_json: true}")

            with self.assertRaises(json.JSONDecodeError):
                LLMConvData.from_json_file(temp.name)



    def test_missing_required_fields(self):
        temp = tempfile.NamedTemporaryFile()
        # Test case with missing required fields in JSON data
        incomplete_data = {
            "context": "Incomplete data",
            "user_names": ["User1"],
            # Missing 'user_attributes' and 'user_instructions'
        }
        with open(temp.name, "w") as f:
            json.dump(incomplete_data, f)

        with self.assertRaises(TypeError):
            LLMConvData.from_json_file(temp.name)



class TestLLMConvGenerator(unittest.TestCase):

    def setUp(self):
        # Sample data for LLMConvData
        self.data = LLMConvData(
            context="This is the conversation context.",
            user_names=["Alice", "Bob"],
            user_attributes=[["Analytical"], ["Creative"]],
            user_instructions="Focus on engaging dialogue.",
            turn_manager_type="round_robin",
            turn_manager_config={"some_config": 1.0},
            conv_len=4,
            history_ctx_len=3,
            moderator_name="Moderator",
            moderator_attributes=["Impartial"],
            moderator_instructions="Ensure fair conversation."
        )

        # Mock models
        self.mock_user_model = MagicMock(spec=LlamaModel)
        self.mock_moderator_model = MagicMock(spec=LlamaModel)

    def test_initialization_with_moderator(self):
        # Initialize generator with moderator
        generator = LLMConvGenerator(self.data, self.mock_user_model, self.mock_moderator_model)
        self.assertEqual(generator.data, self.data)
        self.assertEqual(generator.user_model, self.mock_user_model)
        self.assertEqual(generator.moderator_model, self.mock_moderator_model)

    def test_initialization_without_moderator(self):
        # Modify data to exclude moderator and initialize
        self.data.moderator_name = None
        self.data.moderator_attributes = None
        self.data.moderator_instructions = None

        generator = LLMConvGenerator(self.data, self.mock_user_model, None)
        self.assertEqual(generator.moderator_model, None)

    def test_error_on_missing_user_model(self):
        # Check that initialization fails if the user model is None
        with self.assertRaises(AssertionError):
            LLMConvGenerator(self.data, None, self.mock_moderator_model) # type: ignore

    def test_error_on_missing_moderator_model_with_moderator_name(self):
        # Check that initialization fails if moderator model is missing but moderator data exists
        with self.assertRaises(AssertionError):
            LLMConvGenerator(self.data, self.mock_user_model, None)

    @patch(turn_manager.__name__ + '.turn_manager_factory')
    def test_produce_conversation(self, mock_turn_manager_factory):
        # Mock the turn manager factory
        mock_turn_manager = MagicMock()
        mock_turn_manager_factory.return_value = mock_turn_manager

        generator = LLMConvGenerator(self.data, self.mock_user_model, self.mock_moderator_model)

        # Generate conversation
        generated_conv = generator.produce_conversation()

        # Verify that a Conversation instance was created with expected properties
        self.assertIsInstance(generated_conv, Conversation)
        self.assertEqual(generated_conv.ctx_history.maxlen, self.data.history_ctx_len)
        self.assertEqual(generated_conv.conv_len, self.data.conv_len)
        self.assertEqual(generated_conv.next_turn_manager, mock_turn_manager)

        # Check users
        self.assertEqual(len(generated_conv.username_user_map), len(self.data.user_names))
        for i, user_obj in enumerate(generated_conv.username_user_map.values()):
            # TODO: maybe remove IActor at this point
            self.assertIsInstance(user_obj, LLMUser)
            self.assertEqual(user_obj.name, self.data.user_names[i]) # type: ignore
            self.assertEqual(user_obj.attributes, self.data.user_attributes[i]) # type: ignore
            self.assertEqual(user_obj.instructions, self.data.user_instructions) # type: ignore
            self.assertEqual(user_obj.context, self.data.context) # type: ignore

        # Check moderator
        self.assertIsInstance(generated_conv.moderator, LLMUser)
        self.assertEqual(generated_conv.moderator.name, self.data.moderator_name) # type: ignore
        self.assertEqual(generated_conv.moderator.attributes, self.data.moderator_attributes) # type: ignore
        self.assertEqual(generated_conv.moderator.instructions, self.data.moderator_instructions) # type: ignore

    @patch(turn_manager.__name__ + '.turn_manager_factory')
    def test_produce_conversation_without_moderator(self, mock_turn_manager_factory):
        # Modify data to exclude moderator
        self.data.moderator_name = None
        self.data.moderator_attributes = None
        self.data.moderator_instructions = None

        generator = LLMConvGenerator(self.data, self.mock_user_model, None)

        # Generate conversation
        generated_conv = generator.produce_conversation()

        # Verify that a Conversation instance was created without a moderator
        self.assertIsInstance(generated_conv, Conversation)
        self.assertIsNone(generated_conv.moderator)


class TestConversationSeedOpinions(unittest.TestCase):
    def setUp(self):
        # Mock turn manager
        self.mock_turn_manager = MagicMock()
        self.mock_turn_manager.next_turn_username.side_effect = ["User1", "User2", "User1", "User2"]

        # Mock users
        self.user1 = MagicMock()
        self.user1.get_name.return_value = "User1"
        self.user1.speak.return_value = "User1's message"

        self.user2 = MagicMock()
        self.user2.get_name.return_value = "User2"
        self.user2.speak.return_value = "User2's message"

        self.moderator = MagicMock()
        self.moderator.get_name.return_value = "Moderator"
        self.moderator.speak.return_value = "Moderator's comment"

    def test_correct_archival_of_seed_opinions(self):
        seed_opinions = ["Seed message 1", "Seed message 2"]
        seed_users = ["SeedUser1", "SeedUser2"]
        conversation = Conversation(
            turn_manager=self.mock_turn_manager,
            users=[self.user1, self.user2],
            moderator=self.moderator,
            seed_opinions=seed_opinions,
            seed_opinion_users=seed_users,
            conv_len=2,
            history_context_len=10
        )

        conversation.begin_conversation(verbose=False)

        # Verify seed opinions are archived correctly
        
        self.assertEqual(conversation.conv_logs[0], {'name': 'SeedUser1', 'text': 'Seed message 1', 'model': None})
        self.assertEqual(conversation.conv_logs[1], {'name': 'SeedUser2', 'text': 'Seed message 2', 'model': None})

        # Verify conversation history includes seed opinions
        self.assertEqual(conversation.ctx_history[0], output_util.format_chat_message("SeedUser1", "Seed message 1"))
        self.assertEqual(conversation.ctx_history[1], output_util.format_chat_message("SeedUser2", "Seed message 2"))

    def test_validation_of_seed_opinions_length(self):
        # Mismatched lengths
        with self.assertRaises(ValueError):
            Conversation(
                turn_manager=self.mock_turn_manager,
                users=[self.user1, self.user2],
                seed_opinions=["Seed message 1"],
                seed_opinion_users=["User1", "User2"],
                conv_len=2,
            )

        # Exceeding history context length
        with self.assertRaises(ValueError):
            Conversation(
                turn_manager=self.mock_turn_manager,
                users=[self.user1, self.user2],
                seed_opinions=["Seed message 1", "Seed message 2", "Seed message 3"],
                seed_opinion_users=["User1", "User2", "User1"],
                history_context_len=2,
                conv_len=2,
            )

    def test_empty_seed_opinions(self):
        conversation = Conversation(
            turn_manager=self.mock_turn_manager,
            users=[self.user1, self.user2],
            conv_len=2,
        )

        conversation.begin_conversation(verbose=False)

        # Verify no seed opinions are added
        self.assertEqual(len(conversation.conv_logs), 2)  # 2 rounds, 1 user per round
        self.assertEqual(conversation.ctx_history.maxlen, 5)  # Default context length

    def test_seed_opinions_with_moderator(self):
        seed_opinions = ["Seed message 1", "Seed message 2"]
        seed_users = ["SeedUser1", "SeedUser2"]
        conversation = Conversation(
            turn_manager=self.mock_turn_manager,
            users=[self.user1, self.user2],
            moderator=self.moderator,
            seed_opinions=seed_opinions,
            seed_opinion_users=seed_users,
            conv_len=2,
        )

        conversation.begin_conversation(verbose=False)

        # Verify moderator responds after seed opinions
        expected_logs = [
            {'name': 'SeedUser1', 'text': 'Seed message 1', 'model': None},
            {'name': 'SeedUser2', 'text': 'Seed message 2', 'model': None}
        ]
        self.assertListEqual(conversation.conv_logs[:2], expected_logs)

    def test_seed_opinions_integration_with_conversation_flow(self):
        seed_opinions = ["Seed message 1"]
        seed_users = ["SeedUser1"]
        conversation = Conversation(
            turn_manager=self.mock_turn_manager,
            users=[self.user1, self.user2],
            seed_opinions=seed_opinions,
            seed_opinion_users=seed_users,
            conv_len=2,
        )

        conversation.begin_conversation(verbose=False)

        # Verify the conversation continues seamlessly after seed opinions
        expected_logs = [
            {'name': 'SeedUser1', 'text': 'Seed message 1', 'model': None},
        ]
        self.assertEqual(conversation.conv_logs[0], expected_logs[0])
        self.assertEqual(len(conversation.conv_logs), 3)


if __name__ == "__main__":
    unittest.main()
