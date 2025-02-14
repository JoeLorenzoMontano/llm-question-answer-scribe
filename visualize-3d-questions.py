import psycopg2
import numpy as np
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA
from mpl_toolkits.mplot3d import Axes3D
import random

def fetch_questions_answers():
    """Fetches questions and their corresponding answers from the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host="localhost", port="5432", dbname="ollama_db", user="user", password="password"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT q.question_id, q.question_text, a.answer_text FROM questions q LEFT JOIN answers a ON q.question_id = a.question_id;")
        data = cursor.fetchall()
        cursor.close()
        conn.close()

        # Organize data
        questions = []
        answers = []
        question_answer_pairs = []  # List of (question_idx, answer_idx) tuples

        q_index_map = {}  # Map question_id -> index in questions list
        for q_id, question_text, answer_text in data:
            if question_text and q_id not in q_index_map:
                q_index_map[q_id] = len(questions)
                questions.append(question_text)
            
            if answer_text:
                answers.append(answer_text)
                question_answer_pairs.append((q_index_map[q_id], len(questions) + len(answers) - 1))  # Pair index

        return questions, answers, question_answer_pairs

    except Exception as e:
        print("Error fetching questions and answers:", e)
        return [], [], []

def visualize_questions_answers(questions, answers, question_answer_pairs):
    """Processes and visualizes questions and answers in 3D space with color grouping."""
    if not questions and not answers:
        print("No data found in the database.")
        return

    # Combine questions and answers for processing
    all_texts = questions + answers

    # Convert questions and answers into numerical vectors using TF-IDF
    vectorizer = TfidfVectorizer()
    X_tfidf = vectorizer.fit_transform(all_texts)

    # Reduce dimensionality to 3D using PCA
    pca = PCA(n_components=3)
    X_3d = pca.fit_transform(X_tfidf.toarray())

    # Generate unique colors for each question-answer pair
    unique_colors = ["red", "blue", "green", "purple", "orange", "brown", "pink", "gray", "cyan", "magenta"]
    color_map = {}  # Maps question index to color

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')

    # Plot questions
    for q_idx, question in enumerate(questions):
        color = color_map.get(q_idx, random.choice(unique_colors))  # Assign color if not already assigned
        color_map[q_idx] = color
        ax.scatter(X_3d[q_idx, 0], X_3d[q_idx, 1], X_3d[q_idx, 2], c=color, marker='o', label=f"Q{q_idx+1}")
        ax.text(X_3d[q_idx, 0], X_3d[q_idx, 1], X_3d[q_idx, 2], f"Q{q_idx+1}", fontsize=9)

    # Plot answers and connect them to their questions
    for q_idx, a_idx in question_answer_pairs:
        color = color_map.get(q_idx, "black")  # Use the same color as the question
        ax.scatter(X_3d[a_idx, 0], X_3d[a_idx, 1], X_3d[a_idx, 2], c=color, marker='x', label=f"A{a_idx+1}")
        ax.text(X_3d[a_idx, 0], X_3d[a_idx, 1], X_3d[a_idx, 2], f"A{a_idx+1}", fontsize=9)
        
        # Draw a line connecting the question and its answer
        ax.plot([X_3d[q_idx, 0], X_3d[a_idx, 0]], 
                [X_3d[q_idx, 1], X_3d[a_idx, 1]], 
                [X_3d[q_idx, 2], X_3d[a_idx, 2]], 
                color=color, linestyle="--", linewidth=0.8)

    # Labels
    ax.set_xlabel("PCA 1")
    ax.set_ylabel("PCA 2")
    ax.set_zlabel("PCA 3")
    ax.set_title("3D Representation of Questions and Answers")

    # Move the legend outside the plot
    plt.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=9, frameon=True)

    plt.show()

def main():
    """Runs the visualization."""
    # Fetch questions and answers from the database
    questions, answers, question_answer_pairs = fetch_questions_answers()

    # Visualize questions and answers
    visualize_questions_answers(questions, answers, question_answer_pairs)

if __name__ == "__main__":
    main()
