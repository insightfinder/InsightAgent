import config
from output.grpc import GrpcOutput
from source.file import FileSource


def main():
    if config.INPUT_TYPE == "file":
        source = FileSource(config.FILE_INPUT_FOLDER)
    else:
        raise ValueError(f"Unsupported input type: {config.INPUT_TYPE}")

    output = GrpcOutput(
        config.OUTPUT_ENDPOINT,
        insecure=config.OUTPUT_GRPC_INSECURE,
        max_message_size=config.OUTPUT_GRPC_MAX_MESSAGE_SIZE,
    )
    try:
        output.send(source.get_spans())
    finally:
        output.close()


if __name__ == "__main__":
    main()
