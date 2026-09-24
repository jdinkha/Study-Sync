# StudySync

## AI Powered Note Generation App

Upload your lecture PDFs and generate study cards with AI

## Prerequisites
1. **Python**
2. **Node.js/Vite**
3. **Ollama**

## Quick start

1. Clone the repo to your machine

2. Install Ollama: ollama.com

By default the program will use Mistral, you can change the model by editing backend/main.py

3. Start the app, from the project root:

- **Terminal 3**:
cd backend
pip install -r requirements.txt
python3 main.py

- **Terminal 4**:
cd frontend
npm install
npm run dev

- **Browser**:
Vite tells you which port the program runs, but by default it is localhost:5173


## Architecture
- **Frontend**: TypeScript + React + Vite
- **Backend**: Python
- **Storage**: SQLite
- Local LLM integration with Ollama
