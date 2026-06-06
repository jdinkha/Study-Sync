# StudySync

## AI Powered Note Generation App

## Quick start

1. Clone the repo to your machine

2. Install Ollama: ollama.com

3. Download and run a model of your choice
for example, to download and run Mistral 7B:

Terminal 1:
'ollama serve'

Terminal 2:
'ollama run mistral'

4. Start the app, from the project root:

Terminal 3:
cd backend
pip install -r requirements.txt
python3 main.py

Terminal 4:
cd frontend
npm install
npm run dev


## Architecture
- **Frontend**: TypeScript + React + Vite
- **Backend**: Python
- **Storage** SQLite
- Local LLM integration with Ollama
