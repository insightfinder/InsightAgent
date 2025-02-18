import os
import re
import requests
import yaml
import logging
from langchain_community.document_loaders import UnstructuredMarkdownLoader

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

def process_rag_files(dir: str, company_name: str, dataset_name: str):
    rag_files = []
    for filename in os.listdir(dir):
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
        break
    return {"company":company_name,"dataset":dataset_name,"doc_list":rag_files}


def main():
    """Main entry point for the Python agent."""
    # Get the input string from command-line arguments
    api_config = config["api"]
    dir = api_config["dir"]
    company_name = api_config["company"]
    dataset_name = api_config["dataset"]
    genAI_addr = api_config["GenAI_address"]
    log_config = config["logging"]
    logging.basicConfig(filename=log_config["file"], level=log_config["level"], 
                    format='%(asctime)s - %(levelname)s - %(message)s')

    headers = {"accept": "application/json","Content-Type": "application/json"}
    rag_dto = process_rag_files(dir, company_name, dataset_name)
    url = genAI_addr + "/rag-dataset-uploader/rag-dataset-uploader"
    response = requests.post(url, json=rag_dto, headers=headers)
    logging.info("API Response status: %d, msg: %s", response.status_code, response.json()["detail"])


if __name__ == "__main__":
    main()