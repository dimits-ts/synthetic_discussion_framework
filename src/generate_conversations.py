import argparse
import os
import yaml
import logging
from pathlib import Path

from sdl.serialization import conversation_io
from sdl.util import file_util
from sdl.util.logging_util import logging_setup


logger = logging.getLogger(Path(__file__).name)


def process_file(input_file, output_dir, model):
    try:
        logger.info(f"Processing file: {input_file}")
        # Load data and start conversation
        data = conversation_io.LLMConvData.from_json_file(input_file)
        generator = conversation_io.LLMConvGenerator(
            data=data, user_model=model, moderator_model=model
        )
        conv = generator.produce_conversation()

        logger.info("Beginning conversation...")
        conv.begin_conversation(verbose=True)
        output_path = file_util.generate_datetime_filename(
            output_dir=output_dir, file_ending=".json"
        )
        conv.to_json_file(output_path)
        logger.info("Conversation saved to ", output_path)
    except Exception:
        logger.exception("Experiment aborted due to error.")


def main():
    # Set up argument parser for config file path
    parser = argparse.ArgumentParser(description="Generate synthetic conversations")
    parser.add_argument(
        "--config_file",
        required=True,
        help="Path to the YAML configuration file",
    )
    args = parser.parse_args()

    # Load configuration from YAML file
    with open(args.config_file, "r") as file:
        config_data = yaml.safe_load(file)

    paths = config_data["generate_conversations"]["paths"]
    model_params = config_data["generate_conversations"]["model_parameters"]
    logging_config = config_data["logging"]

    logging_setup(
        print_to_terminal=logging_config["print_to_terminal"],
        write_to_file=logging_config["write_to_file"],
        logs_dir=logging_config["logs_dir"],
        level=logging_config["level"]
    )

    # Extract values from the config
    input_dir = Path(paths["input_dir"])
    output_dir = Path(paths["output_dir"])
    model_path = paths["model_path"]

    model_name = model_params["general"]["model_name"]
    library_type = model_params["general"]["library_type"]
    max_tokens = model_params["general"]["max_tokens"]
    ctx_width_tokens = model_params["general"]["ctx_width_tokens"]
    remove_str_list = model_params["general"]["disallowed_strings"]

    inference_threads = model_params["llama_cpp"]["inference_threads"]
    gpu_layers = model_params["llama_cpp"]["gpu_layers"]

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Check if input directory exists
    if not input_dir.is_dir():
        logger.error(f"Error: Input directory '{input_dir}' does not exist.")
        exit(1)

    # Load model based on type
    logger.info("Loading LLM...")

    model = None
    if library_type == "llama_cpp":
        from sdl.backend.cpp_model import LlamaModel # dynamically load library to avoid dependency hell

        model = LlamaModel(
            model_path=model_path,
            name=model_name,
            max_out_tokens=max_tokens,
            seed=42,  # Random seed (this can be adjusted)
            remove_string_list=remove_str_list,
            ctx_width_tokens=ctx_width_tokens,
            inference_threads=inference_threads,
            gpu_layers=gpu_layers,
        )
    elif library_type == "transformers":
        from sdl.backend.trans_model import TransformersModel # dynamically load library to avoid dependency hell

        model = TransformersModel(
            model_path=model_path,
            name=model_name,
            max_out_tokens=max_tokens,
            remove_string_list=remove_str_list,
        )
    else:
        raise NotImplementedError(f"Unknown model type: {library_type}. Supported types: llama_cpp, transformers")

    logger.info("Model loaded.")

    # Process the files in the input directory
    logger.info(f"Starting experiments...")

    for input_file in input_dir.glob("*.json"):
        if input_file.is_file():
            process_file(input_file, output_dir, model)
        else:
            logger.warning(f"Skipping non-file entry: {input_file}")

    logger.info(f"Finished experiments.")


if __name__ == "__main__":
    main()
