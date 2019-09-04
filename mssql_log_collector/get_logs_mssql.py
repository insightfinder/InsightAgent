from configparser import SafeConfigParser
from datetime import datetime
import os
import sys
import pytz
import Constant
import json
import requests
import time
import traceback
import pyodbc


'''
Check if all the config parameters are not empty
'''
def check_config_parameters(config_map):
    for key in config_map:
        if len(config_map[key]) == 0:
            print("Agent not correctly configured. Check config file for" + str(key))
            sys.exit(1)


'''
Get the parameters from the config files
'''
def get_config_map():
    mssql_config_map = {}
    if_config_map = {}
    home_path = os.getcwd()
    try:
        if os.path.exists(os.path.join(home_path, Constant.CONFIG_FILE)):
            parser = SafeConfigParser()
            parser.read(os.path.join(home_path, Constant.CONFIG_FILE))
            # MSSql config
            mssql_config_map[Constant.HOST_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.HOST_CONFIG)
            mssql_config_map[Constant.DATABASE_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.DATABASE_CONFIG)
            mssql_config_map[Constant.USER_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.USER_CONFIG)
            mssql_config_map[Constant.PASSWORD_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.PASSWORD_CONFIG)
            mssql_config_map[Constant.TABLE_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.TABLE_CONFIG)
            mssql_config_map[Constant.INSTANCE_NAME_FIELD_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.INSTANCE_NAME_FIELD_CONFIG)
            mssql_config_map[Constant.TIMESTAMP_FIELD_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.TIMESTAMP_FIELD_CONFIG)
            mssql_config_map[Constant.TIMESTAMP_FORMAT_CONFIG] = parser.get(Constant.MSSQL_TAG, Constant.TIMESTAMP_FORMAT_CONFIG, raw=True)
            check_config_parameters(mssql_config_map)
            # InsightFinder config
            if_config_map[Constant.LICENSE_KEY_CONFIG] = parser.get(Constant.IF_TAG, Constant.LICENSE_KEY_CONFIG)
            if_config_map[Constant.PROJECT_NAME_CONFIG] = parser.get(Constant.IF_TAG, Constant.PROJECT_NAME_CONFIG)
            if_config_map[Constant.USER_NAME_CONFIG] = parser.get(Constant.IF_TAG, Constant.USER_NAME_CONFIG)
            if_config_map[Constant.SERVER_URL_CONFIG] = parser.get(Constant.IF_TAG, Constant.SERVER_URL_CONFIG)
            if_config_map[Constant.SAMPLING_INTERVAL] = parser.get(Constant.IF_TAG, Constant.SAMPLING_INTERVAL)
            check_config_parameters(if_config_map)
            print("Loaded all parameters from config file")
    except IOError:
        print("config.ini file is missing")
    return mssql_config_map, if_config_map


'''
Connect to the database by the given credentials
'''
def connect_to_database(host, database, user, password):
    try:
        connection = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER='+host+';DATABASE='+database+';UID='+user+';PWD='+ password)
        return connection
    except Exception as e:
        print ("Error while connecting to database", e)


'''
Close the given database connectection 
'''
def close_database_connection(connection):
    # closing database connection.
     connection.close()
     print("MSSQL connection is closed")


'''
Get the map of column name and its corresponding index in the table schema
'''
def get_column_name_map(cursor, table, timestamp_column):
    column_name_map = {}
    cursor.execute("select COLUMN_NAME from INFORMATION_SCHEMA.COLUMNS where TABLE_NAME= '%s' "% (table))
    column_names = cursor.fetchall()
    print(column_names)
    index = 0
    for column_name in column_names:
        column_name_map[column_name[0]] = index
        index += 1
    if timestamp_column not in column_name_map:
        print("Wrong timestamp column specifed in the config file, got " + timestamp_column)
        print("Table schema is " + str([column_names[i][0] for i in range(len(column_names))]))
        sys.exit(1)
    return column_name_map


'''
Given a date string and date format, return the epoch time
'''
def get_gmt_timestamp(date_string, datetime_format):
    if datetime_format == Constant.NONE:
        return long(date_string)
    struct_time = datetime.strptime(date_string, datetime_format)
    time_by_zone = pytz.timezone(Constant.GMT).localize(struct_time)
    epoch = long((time_by_zone - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch


'''
Get date time by the given timestamp_format
'''
def get_sql_query_time(timestamp, timestamp_format):
    if timestamp_format == Constant.NONE:
        return str(timestamp)
    else:
        return "\'" + time.strftime(timestamp_format, time.gmtime(timestamp / 1000.0)) + "\'"


'''
By the given query row result, generate the raw data object
'''
def get_raw_data(row, column_name_map, columns_to_filter):
    raw_data = {}
    for key in column_name_map.keys():
        if key not in columns_to_filter:
            raw_data[key] = str(row[column_name_map[key]])
    return raw_data


'''
Get the instance name from the query if exists, if not using the table name as the instance/host for the collected log
'''
def get_instance_name(row, instance_column, column_name_map, table):
    if instance_column in column_name_map:
        return row[column_name_map[instance_column]]
    else:
        return table


'''
Get current timestamp
'''
def get_current_time():
    return time.time() * 1000


'''
Get the query result from the table by the given table, timestamp
'''
def get_rows_from_table(cursor, table, timestamp_column, timestamp_format, start_time, end_time):
    converted_start_time = get_sql_query_time(start_time, timestamp_format)
    converted_end_time = get_sql_query_time(end_time, timestamp_format)
    statement = "SELECT * FROM " + table + " WHERE " + timestamp_column + " >= " + converted_start_time + " AND " + timestamp_column + " <= " + converted_end_time
    print("Perform sql query: " + statement)
    cursor.execute(statement)
    rows = cursor.fetchall()
    return rows


'''
Query the log event from the given table, using the given parameters to generate the log event
'''
def get_log_events(cursor, table, instance_column, timestamp_column, timestamp_format, start_time, end_time):
    events = []
    column_name_map = get_column_name_map(cursor, table, timestamp_column)
    rows = get_rows_from_table(cursor, table, timestamp_column, timestamp_format, start_time, end_time)
    columns_to_filter = [instance_column, timestamp_column]
    for row in rows:
        event = {}
        event[Constant.RAW_DATA_KEY] = get_raw_data(row, column_name_map, columns_to_filter)
        event[Constant.TIMESTAMP_KEY] = get_gmt_timestamp(str(row[column_name_map[timestamp_column]]), timestamp_format)
        event[Constant.INSTANCE_NAME_KEY] = get_instance_name(row, instance_column, column_name_map, table)
        events.append(event)
    cursor.close()
    print("Collected events number: " + str(len(events)))
    return events


'''
Send the collected log to the IF system
'''
def send_chunk_data(config, events_to_send):
    # generate the json object send to the IF system
    to_send_data_dict = dict()
    to_send_data_dict[Constant.METRIC_DATA] = json.dumps(events_to_send)
    to_send_data_dict[Constant.LICENSE_KEY] = config[Constant.LICENSE_KEY_CONFIG]
    to_send_data_dict[Constant.PROJECT_NAME] = config[Constant.PROJECT_NAME_CONFIG]
    to_send_data_dict[Constant.USER_NAME] = config[Constant.USER_NAME_CONFIG]
    to_send_data_dict[Constant.AGENT_TYPE] = Constant.AGENT_TYPE_LOG_STREAMING
    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config[Constant.SERVER_URL_CONFIG] + Constant.CUSTOM_PROJECT_RAW_DATA_URL
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == Constant.SUCCESS_CODE:
        print("Send data successfully, size: " + str(len(str(to_send_data_dict))))
    else:
        print("Got status code: " + str(response.status_code))


'''
Chunk the data
'''
def send_data(events, config):
    events_to_send = []
    for event in events:
        events_to_send.append(event)
        if len(events_to_send) >= Constant.CHUNK_SIZE:
            send_chunk_data(config, events_to_send)
            events_to_send = []
    if len(events_to_send) != 0:
        send_chunk_data(config, events_to_send)


if __name__ == "__main__":
    configs = get_config_map()
    mssql_config = configs[0]
    if_config = configs[1]
    end_time = get_current_time()
    start_time = end_time - Constant.ONE_MINUTE * int(if_config[Constant.SAMPLING_INTERVAL])
    try:
        connection = connect_to_database(mssql_config[Constant.HOST_CONFIG],
                                         mssql_config[Constant.DATABASE_CONFIG],
                                         mssql_config[Constant.USER_CONFIG],
                                         mssql_config[Constant.PASSWORD_CONFIG])
        events = get_log_events(connection.cursor(), mssql_config[Constant.TABLE_CONFIG],
                                mssql_config[Constant.INSTANCE_NAME_FIELD_CONFIG],
                                mssql_config[Constant.TIMESTAMP_FIELD_CONFIG],
                                mssql_config[Constant.TIMESTAMP_FORMAT_CONFIG],
                                start_time, end_time)
        send_data(events, if_config)
        close_database_connection(connection)
    except Exception as e:
        traceback.print_exc()

