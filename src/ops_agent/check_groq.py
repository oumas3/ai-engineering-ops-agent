import asyncio
import os
from time import perf_counter

from groq import AsyncGroq

from ops_agent.models import InvestigationAnalysis


async def main() -> None:
    async with AsyncGroq(
        api_key=os.environ["GROQ_API_KEY"],
        max_retries=0,
    ) as client:
        started = perf_counter()

        try:
            async with asyncio.timeout(20):
                response = await client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[
                        {
                            "role": "system",
                   "content": (
                        "Analyse engineering evidence conservatively. "
                        "Observations must contain only supplied facts. "
                        "Put missing evidence in limitations. "
                        "Return at most two hypotheses; an empty list is acceptable. "
                        "Each hypothesis must explain its connection to an observation "
                        "and remain explicitly uncertain. "
                        "Do not assume unmentioned infrastructure, such as load balancers "
                        "or multiple application nodes. "
                        "An HTTP response does not by itself prove the application "
                        "process is stopped or running correctly. "
                        "Recommend at most three specific checks that address the "
                        "supplied evidence or missing information. "
                        "Do not claim that suggested checks were performed. "
                        "Keep every item concise."
),
                        },
                        {
                            "role": "user",
                        "content": (
                            "System context: this is a local Docker Compose project. "
                            "The services are named backend and database. "
                            "The backend uses FastAPI. Its /ready handler queries the "
                            "database and returns HTTP 503 when that database check fails. "
                            "The test calls the backend directly through its published port. "
                            "Observed evidence: GET /ready returned HTTP 503. "
                            "No backend logs or database status were collected for this run."
                        ),
                        },
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "investigation_analysis",
                            "strict": True,
                            "schema": (
                                InvestigationAnalysis.model_json_schema()
                            ),
                        },
                    },
                    reasoning_effort="low",
                    max_completion_tokens=1024,
                )
        except TimeoutError:
            print("Groq did not finish within the 20-second deadline.")
            return

        elapsed = perf_counter() - started

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError("Groq did not finish the analysis normally.")

    content = choice.message.content

    if not content:
        raise ValueError("Groq returned no analysis content.")

    analysis = InvestigationAnalysis.model_validate_json(content)

    print(analysis.model_dump_json(indent=2))
    print(f"Request duration: {elapsed:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())