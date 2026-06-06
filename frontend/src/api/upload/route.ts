import { writeFile } from "fs/promises";
import path from "path";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;
    const deckName = formData.get("deckName") as string;

    if (!file || !deckName) {
      return NextResponse.json(
        { message: "Missing file or deck name" },
        { status: 400 }
      );
    }

    if (!file.name.endsWith(".pdf")) {
      return NextResponse.json(
        { message: "Only PDF files are supported" },
        { status: 400 }
      );
    }

    // Save the file temporarily
    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    const filename = `${Date.now()}_${file.name}`;
    const filepath = path.join("/tmp", filename);

    await writeFile(filepath, buffer);

    // Call Python backend to ingest
    const response = await fetch("http://localhost:8000/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filepath,
        deckName,
        userId: "user123", // get from session/auth
      }),
    });

    if (!response.ok) {
      throw new Error("Ingestion failed");
    }

    const result = await response.json();

    return NextResponse.json({
      deckId: result.deckId,
      cardCount: result.cardCount,
    });
  } catch (error) {
    console.error(error);
    return NextResponse.json(
      { message: "Upload failed" },
      { status: 500 }
    );
  }
}
