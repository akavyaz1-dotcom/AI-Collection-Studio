\# AI Collection Studio



AI-assisted pipeline for producing collectible illustrations for casual mobile games.



Developed as a prototype for the Playrix AI-pilled Production Producer test assignment.



\## Features



\- Generate 3–5 themed collection concepts from a producer's brief.

\- Generate 10 collectible objects per set.

\- Assign composition categories and create individual image prompts.

\- Store collections, prompts and uploaded illustrations.

\- Run technical image validation and AI-assisted visual quality checks.

\- Export generated illustrations as ZIP archives.



\## Technology



\- Python

\- Streamlit

\- GigaChat API

\- SQLite

\- Pillow



\## Installation



1\. Install Python.

2\. Install dependencies:



&#x20;  `pip install -r requirements.txt`



3\. Create a `.env` file in the project root:



&#x20;  `GIGACHAT\_AUTH\_KEY=your\_api\_key\_here`



4\. Launch the application from the project root:



&#x20;  `python -m streamlit run deploy/app.py --server.port 8502`



5\. Open `http://localhost:8502` in your browser.



\## Workflow



1\. Enter a collection theme and optional producer instructions.

2\. Select the number of collection variants.

3\. Generate themed sets and review the proposed objects.

4\. Use the generated prompts to create illustrations in an external image-generation service.

5\. Upload the illustrations to AI Collection Studio.

6\. Run technical and AI-assisted quality checks.

7\. Export the approved illustrations.



\## Current limitations



Image generation currently requires an external service and manual image upload. The prototype does not provide fully autonomous end-to-end image generation.



The tool supports production preparation, structured prompt generation, asset management and quality control.



\## Deliverables



Three cinema-themed sets were prepared for the assignment:



\- Pirate Adventure

\- Hollywood Cinema

\- Spy Thriller



Each set contains 10 collectible illustrations. The final visual comparison and production process are documented on the accompanying Miro board.

