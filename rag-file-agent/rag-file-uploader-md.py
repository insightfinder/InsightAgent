import os
import re
import requests
import yaml
import logging
from langchain_community.document_loaders import UnstructuredMarkdownLoader

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

def process_rag_files(dir: str, company_name: str, dataset_name: str, filename_list: list[str]):
    rag_files = []
    for filename in filename_list:
        path = os.path.join(dir, filename)
        hex = None
        with open(os.path.join(dir, filename), "r") as f:
            loader = UnstructuredMarkdownLoader(path)
            documents = loader.load()
            if dataset_name == "Microsoft Documents":
                match = re.search(r'0x[0-9a-fA-F]+', filename)
                if match:
                    hex = match.group()
                else:
                    hex = filename
        rag_files.append({"filename":filename,"tags":hex,"content":documents[0].page_content})
    return {"company":company_name,"dataset":dataset_name,"doc_list":rag_files}

def chunk_filename_list(dir: str, chunk_size: int):
    lst = os.listdir(dir)
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def main():
    """Main entry point for the Python agent."""
    # Get the input string from command-line arguments
    required_keys = ["api", "logging"]
    if not all(key in config for key in required_keys):
        raise KeyError(f"Missing required config keys: {required_keys}")
    api_config = config["api"]
    dir = api_config["dir"]
    company_name = api_config["company"]
    dataset_name = api_config["dataset"]
    genAI_addr = api_config["GenAI_address"]
    log_config = config["logging"]
    chunk_size = config["agent"]["chunk_size"]
    logging.basicConfig(filename=log_config["file"], level=log_config["level"], 
                    format='%(asctime)s - %(levelname)s - %(message)s')

    headers = {"accept": "application/json","Content-Type": "application/json"}
    chunked_filename_list = chunk_filename_list(dir, chunk_size)
    for filename_list in chunked_filename_list:
        rag_dto = process_rag_files(dir, company_name, dataset_name, filename_list)
        url = genAI_addr + "/rag-dataset-uploader/rag-dataset-uploader"
        response = requests.post(url, json=rag_dto, headers=headers)
        logging.info("API Response status: %d, msg: %s", response.status_code, response.json()["detail"])


if __name__ == "__main__":
    main()