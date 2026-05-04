#!/usr/bin/env python3
"""Initialize MSSQL test database"""
import pymssql
import time
import sys

def wait_for_mssql(host='localhost', user='sa', password='InsightFinder@01', retries=60):
    """Wait for MSSQL to be ready"""
    for attempt in range(1, retries + 1):
        try:
            conn = pymssql.connect(host=host, user=user, password=password, timeout=5)
            conn.close()
            print("✓ MSSQL is ready!")
            return True
        except Exception as e:
            print(f"Attempt {attempt}/{retries} - waiting for MSSQL...")
            if attempt == retries:
                print(f"✗ Failed to connect after {retries} attempts: {e}")
                return False
            time.sleep(1)

def init_database():
    """Create TestDB and tables with sample data"""
    try:
        # Connect to master to create database (with autocommit)
        conn = pymssql.connect(
            host='localhost',
            user='sa',
            password='InsightFinder@01',
            database='master',
            autocommit=True
        )
        cursor = conn.cursor()

        # Create database
        print("Creating TestDB...")
        cursor.execute("IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'TestDB') CREATE DATABASE TestDB")
        conn.close()

        # Connect to TestDB
        conn = pymssql.connect(
            host='localhost',
            user='sa',
            password='InsightFinder@01',
            database='TestDB'
        )
        cursor = conn.cursor()

        # Create tables
        print("Creating tables...")
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'server_metrics')
        CREATE TABLE server_metrics (
            id INT IDENTITY(1,1) PRIMARY KEY,
            timestamp DATETIME NOT NULL,
            host NVARCHAR(100) NOT NULL,
            cpu_pct DECIMAL(5,2) NOT NULL,
            mem_pct DECIMAL(5,2) NOT NULL,
            disk_io INT NOT NULL
        )
        """)

        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'app_logs')
        CREATE TABLE app_logs (
            id INT IDENTITY(1,1) PRIMARY KEY,
            timestamp DATETIME NOT NULL,
            host NVARCHAR(100) NOT NULL,
            severity NVARCHAR(20) NOT NULL,
            message NVARCHAR(500) NOT NULL
        )
        """)

        # Insert sample data
        print("Inserting sample data...")
        cursor.execute("""
        INSERT INTO server_metrics (timestamp, host, cpu_pct, mem_pct, disk_io) VALUES
        (GETDATE(), 'web-server-01', 72.4, 88.1, 1450),
        (GETDATE(), 'web-server-02', 45.2, 62.0, 890),
        (GETDATE(), 'db-server-01', 55.1, 75.5, 2200)
        """)

        cursor.execute("""
        INSERT INTO app_logs (timestamp, host, severity, message) VALUES
        (GETDATE(), 'web-server-01', 'ERROR', 'Connection pool exhausted after 30s'),
        (GETDATE(), 'web-server-02', 'WARN', 'Retrying DB connection attempt 2/3'),
        (GETDATE(), 'db-server-01', 'INFO', 'Successfully recovered connection')
        """)

        conn.commit()

        # Verify
        cursor.execute("SELECT COUNT(*) FROM server_metrics")
        metrics_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM app_logs")
        logs_count = cursor.fetchone()[0]

        print(f"✓ Initialization complete!")
        print(f"  - Metrics table: {metrics_count} rows")
        print(f"  - Logs table: {logs_count} rows")

        conn.close()
        return True

    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        return False

if __name__ == '__main__':
    if not wait_for_mssql():
        sys.exit(1)
    if not init_database():
        sys.exit(1)
    print("\n✓ Database ready for testing!")
