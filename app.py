import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

client = Hindsight(
    base_url="https://api.hindsight.vectorize.io",
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

BANK_ID = "compliance-audit"

print("Connecting to Hindsight...")

client.retain(
    bank_id=BANK_ID,
    content="Acme Technologies had a missing security policy in its previous compliance audit.",
    context="compliance audit"
)

print("Memory stored successfully.")

result = client.recall(
    bank_id=BANK_ID,
    query="What compliance problem did Acme Technologies have?"
)

print("\nHindsight recalled:")

for memory in result.results:
    print("-", memory.text)