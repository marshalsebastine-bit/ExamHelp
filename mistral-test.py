from mistralai.client import Mistral
import os

with Mistral(
    api_key=os.getenv("MISTRAL_API_KEY", ""),
) as mistral:
    response = mistral.chat.complete(
        model="mistral-large-latest",
        messages=[
            {
                "role": "user",
                "content": "Who is the best French painter? Answer in one short sentence.",
            }
        ],
    )

    print(response.choices[0].message.content)
