import asyncio
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

from sdk import init, sleep, step, workflow

CUSTOMERS = [
    {
        "id": 1,
        "name": "Alice Chen",
        "company": "Acme Corp",
        "pain_point": "deployment pipelines that fail halfway and have to restart from scratch",
    },
    {
        "id": 2,
        "name": "Bob Martinez",
        "company": "Globex",
        "pain_point": "unreliable third-party API calls that leave jobs in unknown states",
    },
    {
        "id": 3,
        "name": "Carol White",
        "company": "Initech",
        "pain_point": "manual recovery when long-running jobs crash overnight",
    },
    {
        "id": 4,
        "name": "David Kim",
        "company": "Umbrella Inc",
        "pain_point": "duplicated work when retrying failed multi-step jobs",
    },
    {
        "id": 5,
        "name": "Eve Johnson",
        "company": "Dunder Mifflin",
        "pain_point": "no visibility into which steps ran before a job failure",
    },
]

client = OpenAI()


@step()
def personalize_email(customer: dict) -> str:
    """LLM call — result is checkpointed. Will not re-run on recovery."""
    print(f"  🤖 Personalizing for {customer['name']}... (LLM call)")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise, personalized outbound sales emails. "
                    "3 sentences max. Be specific to the pain point."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a personalized cold email for {customer['name']} at {customer['company']}. "
                    f"Their main pain point is: {customer['pain_point']}. "
                    "Keep it human and brief."
                ),
            },
        ],
    )
    content = response.choices[0].message.content
    print(f"  ✅ Personalized for {customer['name']}")
    return content


@step()
def send_email(customer: dict, content: str) -> dict:
    """Mock send — checkpointed. Will not re-run on recovery."""
    email = (
        f"{customer['name'].lower().replace(' ', '.')}"
        f"@{customer['company'].lower().replace(' ', '-')}.com"
    )
    print(f"  📧 Sending to {customer['name']} <{email}>")
    print(f"     Preview: {content[:100]}...")
    time.sleep(0.5)
    return {
        "customer_id": customer["id"],
        "email": email,
        "status": "sent",
        "sent_at": time.time(),
    }


@workflow()
async def run_email_campaign(campaign_name: str) -> dict:
    results = []

    for customer in CUSTOMERS:
        print(f"\n[{customer['id']}/5] {customer['name']} @ {customer['company']}")

        content = personalize_email(customer)
        result = send_email(customer, content)
        results.append(result)

        await sleep(1)

    sent_count = len(results)
    print(f"\n✅ Campaign '{campaign_name}' complete — {sent_count} emails sent.")
    return {"campaign": campaign_name, "sent": sent_count, "results": results}


async def main():
    campaign_name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Q2 Outreach"
    print(f"\n🚀 Starting campaign: {campaign_name}\n")
    output = await run_email_campaign(campaign_name)
    print(f"\nFinal output: {output}")


if __name__ == "__main__":
    init(
        name="email-campaign",
        db_url=os.environ.get("DB_URL"),
    )
    asyncio.run(main())
