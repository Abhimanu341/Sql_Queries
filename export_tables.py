import psycopg2
import csv
import logging
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_connection():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
    except Exception as e:
        logging.error(f"Error connecting to the database: {str(e)}")
        return None

def export_table_to_csv(table_name, filename):
    conn = get_db_connection()
    if not conn:
        logging.error("Database connection failed.")
        return

    cur = conn.cursor()
    try:
        with open(filename, 'w', newline='') as file:
            writer = csv.writer(file)
            cur.execute(f"SELECT * FROM {table_name}")
            writer.writerow([desc[0] for desc in cur.description])  # Write header
            writer.writerows(cur.fetchall())  # Write data
        logging.info(f"{table_name} exported to {filename}")
    except Exception as e:
        logging.error(f"Error exporting {table_name}: {str(e)}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    tables = {
        "Teams": "static/teams.csv",
        "Players": "static/players.csv",
        "Matches": "static/matches.csv",
        "Match_Scores": "static/match_scores.csv",
        "Match_Results": "static/match_results.csv"
    }

    for table_name, filename in tables.items():
        export_table_to_csv(table_name, filename)