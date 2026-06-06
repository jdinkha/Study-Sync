from ollama import Client

ollama = Client(host='http://localhost:11434')

@app.post("/api/cards/generate")
async def generate_cards(text: str):
    response = ollama.generate(
        model="MODEL",
        prompt=f"...",
        stream=False
    )
    return {"cards": parse_response(response)}
