import json
import glob
from data_quality_agent.logger import get_logger
import itertools
import polars as pl

logger = get_logger(__name__)

def load_data_from_path(path: str) -> pl.DataFrame:
    filepaths = glob.glob(path)
    logger.info(f"CSV files loading for paths: {', '.join(filepaths)}")
    dfs = []
    for file in filepaths:
        df = pl.read_csv(file, infer_schema=False)
        dfs.append(df)

    return pl.concat(dfs)


def source_to_target_mapping(config: dict, source: str, target: str):

    # Step 1: Load both CSVs into dataframes
    source_df = load_data_from_path(config['paths']['source_data'])
    target_df = load_data_from_path(config['paths']['target_data'])

    logger.info("Loaded CSV files into dataframes")
    
    id_columns = list(config['id_columns'])

    # Creating a composite key called id_key here
    target_df = target_df.with_columns(
        pl.concat_str(id_columns, separator='--').alias('id_key')
    )

    # Prefixing column names with 'target_' to avoid collisions with source columns
    target_df = target_df.rename({col: f"target_{col}" for col in target_df.columns})

    logger.debug(f"Target dtypes: \n{target_df.dtypes}")

    logger.info(f"Created ID keys for Target using cols: {', '.join(id_columns)}")
    logger.debug(f"Target head: \n{target_df}")

    # Injecting rules from configuration for each id_column
    for col in id_columns:
        try:
            logger.info(f"Creating rule from config for column {col}")
            exec(config['rules'][col])
        except Exception as e:
            logger.error(e)

    # Finding function references from locals()
    transformations = { col: locals()[col+'Rule'] for col in id_columns}

    # Applying transformations for each source row
    for col_name, transform_func in transformations.items():
        source_df = source_df.with_columns(
            pl.struct(source_df.columns).map_elements(transform_func, return_dtype=pl.String).alias(col_name+"_source_temp")
        )

    # Modifying names of id_columns generated in source and adding a suffix at the end
    id_columns_transformed = [col + "_source_temp" for col in id_columns]

    # Generating id_key similar to target for the source as well
    source_df = source_df.with_columns(
            pl.concat_str(id_columns_transformed, separator='--').alias('id_key')
    )

    logger.info(f"Generated id_key for the source DF based on id_columns")

    source_df = source_df.drop(id_columns_transformed)
    logger.info(f"Deleted those newly generated columns from source DF: {id_columns_transformed}")

    # Adding prefix to source column to differentiate them from target columns
    source_df = source_df.rename({col: f"source_{col}" for col in source_df.columns})
    logger.debug(f"Source head: \n{source_df}")


    combined_df = source_df.join(target_df, left_on='source_id_key', right_on='target_id_key')

    logger.debug(f"{combined_df}")


    result = []

    combined_rows = None 

    # Checking if additionalModifications is enabled in the config
    if 'additionalModifications' in config:
        code = config['additionalModifications']
        exec(code, globals())
        additionalModifications = globals()['additionalModifications']

        # Get an iterable of rows from the additionalModifications function
        combined_rows = itertools.chain(combined_df.iter_rows(named=True), additionalModifications(config, source_df, target_df))
    else:
        combined_rows = combined_df.iter_rows(named=True)

    # Generating dicts for the combined rows 
    for row in combined_rows:

        timestamp = int(float(row['source_'+config['sourceTimeStampCol']]) * 1000)

        record = {"timestamp": timestamp}

        for col in row.keys():
            if "id_key" in col:
                continue
            system_env, col_name = col.split("_", 1)
            system_mapping = source.lower() if system_env == "source" else target.lower()
            if system_env not in record:
                record[system_env] = {}
            record[system_env][col_name] = row[col]
            record[system_env]['env'] = system_mapping


        result.append(record)

    logger.info(f"Number of matches between Source and Target: {len(result)}")

    # Writing JSON output to the output file
    with open(config['paths']['output'], 'w') as f:
        for record in result:
            f.write(json.dumps(record))
            f.write("\n")

    logger.info("Finished writing records")

