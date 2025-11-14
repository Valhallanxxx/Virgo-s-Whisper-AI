
# ♍ Virgo's Whisper AI

**A conversational AI co-pilot for first responders, designed to reduce cognitive load and provide real-time, stateful guidance during high-stress situations.**



## The Problem

First responders (police, firefighters, paramedics) operate in high-stress environments where information overload is constant. They need to simultaneously manage a crisis, communicate with dispatch, and recall complex, multi-step protocols. This cognitive load can lead to errors and increase personal stress.

## The Solution (Objective)

**Virgo's Whisper AI** is a hands-free, voice-activated "co-pilot" that listens passively in the background. Instead of a simple "question-and-answer" bot, it's a **proactive, conversational guide**.

When a crisis is detected, Virgo engages the user in a stateful, multi-turn conversation to guide them through the correct protocol. It also serves as an automated note-taker and summarizer, allowing the user to focus on the situation at hand. This entire prototype was built on a "No Credit Card" stack, proving that powerful, low-latency AI tools can be made accessible to everyone.

---

## Core Features

This prototype is a complete end-to-end system that supports five major features, all triggered by specific voice keywords.

1.  **Conversational Protocol Guidance:** The AI actively listens for critical protocol keywords. When triggered, it opens a **stateful conversation** (using Firebase as its "short-term memory") to guide the user step-by-step (e.g., "Where are you hurt?") and *understands* their answers ("On my leg") to provide the correct *next* step.

2.  **Manual Voice Notes:** The user can say, "Virgo, **take a note**..." The AI parses this, saves it to the database as a "manual log," and provides an audio confirmation.

3.  **On-Demand Summaries:** The user can ask, "Virgo, **summarize comms**." The AI queries the database for all recent *non-urgent* chatter (`general_comm` logs) and provides a brief audio summary.

4.  **Tactical Debriefs:** The user can ask, "Virgo, **debrief me**." The AI queries the database for all *critical events* (`stress_detected`, `manual_log`) from the past hour and provides a chronological audio debrief.

5.  **Passive Stress Detection:** If the user's voice is analyzed as stressed (but doesn't trigger a protocol), the AI logs the event and provides a simple, private audio prompt: "Deep breath. Focus."

---

## How to Use (Demo Guide)

The system has four modes of interaction. Use the `index.html` demo page and hold the button to speak.

### 1. Passive Listening (Stress Check)
If you say anything that *does not* include a command or keyword, Virgo will passively listen. It will run a simple stress check on your voice.
* **If you sound calm:** It will log your speech as `"general_comm"` and stay silent (you will see a "204 All clear" message).
* **If you sound stressed:** It will log a `"stress_detected"` event and respond with, *"Deep breath. Focus."*

### 2. Standard Commands
You can give Virgo direct orders. These are one-and-done requests.



* **"Virgo, take a note..."**: Triggers the voice note feature.
    * **Example:** "Virgo, take a note: Subject is a male in a red shirt."
    * **Response:** "Note taken: Subject is a male in a red shirt."
* **"Virgo, summarize comms."**: Triggers the summary feature.
    * **Response:** "A test was conducted and reported all clear."
* **"Virgo, debrief me."**: Triggers the tactical debrief.
    * **Response:** "Here is your debrief: Stress detected: Shots fired..."
* **"Over and out."**: This is the master "hang up" command. It will immediately stop any active conversation.
    * **Response:** "Roger that. Virgo out."

### 3. Triggering a Protocol
Speaking any of the pre-defined keywords will **immediately start a conversational protocol**. This takes priority over all other features.



* **Example:** "Shots fired, I am hurt!"
* **Expected Response:** "Please calm down. Tell me where you have been shot."

### 4. Handling a Conversation
Once a protocol is active, the AI is in a stateful chat.
* **Answering Questions:** Simply answer its questions. It will remember the context.
    * **AI:** "Where are you hurt?"
    * **You:** "On my leg."
    * **AI:** "Okay, on your leg. Apply pressure to the wound. Help is on the way."
* **Confusing Answers:** If you give a confusing answer (e.g., "what?"), the AI is designed to rephrase its question instead of looping.
* **Ending the Chat:** You can end the conversation at any time by saying, **"Over and out."**


**Conversational Protocol Guidance**


Protocols

> 1] For "Vehicle Accident (MVA)" 
    *Keywords*: `"accident"`
                             ` "crash"`
                             `"MVA"`
                             `"10-50"`

> 2] For "Shots Fired"
     *Keywords*: `"shots fired"`
                              `"officer down"`
                              `"i got shot"`
                              `"10-31"`

> 3] For "Natural Disaster - Earthquake"
     *Keywords*: `"earthquake"`
                          `"disaster"`
                          `"seismic"`

> 4] For "Robbery in Progress"
     *Keywords*: `"robbery"`
                             `"in progress"`
                             `"10-34"`

> Tactical Debrief :  `"Virgo, debrief me"`

> Summarization:  `"Virgo, summarize comms."`

> Log System:  `"Virgo, take a note"`

> Force Stop:  `"Over and Out"`

---

Category,Feature / Protocol,Trigger Keyword(s)
Protocol,Vehicle Accident (MVA),"accident, crash, MVA, 10-50"
Protocol,Shots Fired,"shots fired, officer down, i got shot, 10-31"
Protocol,Natural Disaster,"earthquake, disaster, seismic"
Protocol,Robbery in Progress,"robbery, in progress, 10-34"
Command,Tactical Debrief,"Virgo, debrief me"
Command,Summarization,"Virgo, summarize comms"
Command,Log System,"Virgo, take a note"
Command,Force Stop,Over and Out

## Architecture & Technology

The system is built on a modular, "no credit card" stack, with each component chosen for a specific purpose.

* **Frontend Demo (The "Body"):** **HTML, CSS, & JavaScript**
    * **Why:** Provides a universal, lightweight, and interactive client that runs in any browser, proving the server's functionality. It uses the browser's `MediaRecorder` API to capture audio.

* **Backend Server (The "Brain"):** **PythonAnywhere (Flask)**
    * **Why:** A free-tier, serverless platform for hosting our Python-based Flask application. It acts as the central router, receiving audio and coordinating all other AI services.

* **Database (The "Memory"):** **Firebase Firestore**
    * **Why:** A fast, real-time, "no credit card" database. It serves three critical memory functions:
        1.  **Long-Term Memory (`protocols`):** Stores the "expert knowledge" (keywords and steps) for all crisis scenarios.
        2.  **Short-Term Memory (`conversations`):** Stores the active chat history, giving the AI stateful, multi-turn conversational ability.
        3.  **Archive (`transcripts`):** Logs every event for later debriefing.

* **Audio Transcription (The "Ears"):** **AssemblyAI**
    * **Why:** Chosen for its high-accuracy, fast speech-to-text transcription and its generous free tier, which is essential for reliably understanding the user's commands.

* **AI & Logic (The "Intelligence"):** **Cerebras**
    * **Why:** Chosen for its **extremely low-latency access** to powerful LLMs (`llama3.1-8b`). This low latency is the most critical factor for a *real-time* co-pilot, allowing the AI to analyze text and provide guidance in seconds. It handles all "intent" routing, conversational logic, and summarization.

* **Voice Generation (The "Voice"):** **ElevenLabs**
    * **Why:** Chosen for its high-quality, realistic, and low-latency voice generation. This allows the AI's response to be clear, calm, and human-sounding, which is essential for a tool designed to be used in high-stress environments.
