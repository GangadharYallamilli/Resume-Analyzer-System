# 🚀 Resume Analyzer System

An AI-powered system that evaluates resumes against job descriptions and generates ATS-based match scores with intelligent feedback and resume optimization.

---

## 📌 Overview

This project automates the resume screening process by combining NLP techniques, a custom scoring algorithm, and Generative AI. It helps identify how well a candidate's resume aligns with a given job description and provides actionable insights to improve it.

---

## ⚙️ System Architecture

User Input (Resume + JD)  
↓  
PDF Text Extraction (PyMuPDF)  
↓  
Text Processing & Keyword Analysis (NLP)  
↓  
Scoring Algorithm (ATS Evaluation)  
↓  
LLM Processing (Feedback & Suggestions)  
↓  
PDF Report Generation (FPDF)  
↓  
Output Delivery  

---

## 🧠 Core Concepts

- **NLP (Natural Language Processing):** Used for text cleaning, keyword extraction, and comparison  
- **LLM (Large Language Model):** Generates human-like feedback and suggestions  
- **ATS Scoring:** Simulates real-world resume screening systems  
- **Prompt Engineering:** Controls AI output quality  

---

## 🛠️ Tech Stack

- Python  
- Generative AI (Google Gemini, HuggingFace)  
- NLP  
- PyMuPDF (PDF parsing)  
- FPDF (PDF generation)  

---

## 🔍 Features

- ATS-based resume scoring  
- Multi-factor evaluation (skills, keywords, experience, domain)  
- AI-generated feedback and improvement suggestions  
- Automated PDF report generation  
- Real-time processing  

---

## 🧮 Scoring Algorithm

The system uses a weighted scoring mechanism:

- Skills Match → 40%  
- Keyword Match → 20%  
- Experience → 20%  
- Domain Fit → 10%  
- AI Evaluation → 10%  

Final score is computed by combining all factors to produce an overall ATS match percentage.

---

## 🤖 How LLM Works in This Project

The system sends structured prompts along with resume and job description data to a language model.

The LLM:
- Understands context  
- Evaluates alignment  
- Generates feedback  
- Suggests improvements  
