import psycopg2
import os
from datetime import datetime

conn = None
try:
    # Connect to the PostgreSQL server
    print('Connecting to the PostgreSQL database...')
    conn = psycopg2.connect(
        host=os.environ.get("DATABASE_URL", "opentelemetry-demo-ffspostgres"),
        dbname='ffs',
        user='ffs',
        password='ffs',
        port=5432
    )

    # Creating a cursor 
    cur = conn.cursor()
    print('Connected to the PostgreSQL database')

    # Update the enabled column where the name is 'recommendationCache'
    cur.execute("UPDATE public.featureflags SET enabled = TRUE WHERE name = 'recommendationCache'")

    # Commit the transaction
    conn.commit()

    # Close the cursor
    cur.close()

    from datetime import datetime

    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    print("Execution Time =", current_time)

except (Exception, psycopg2.DatabaseError) as error:
    print(error)
finally:
    if conn is not None:
        conn.close()
        print('Database connection closed.')
