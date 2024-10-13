import streamlit as st
import requests
from bs4 import BeautifulSoup
import chromadb
from github import Github
import os
from dotenv import load_dotenv
import uuid
from urllib.parse import urljoin

# Load environment variables
load_dotenv()

# Initialize ChromaDB
chroma_client = chromadb.Client()
collection = chroma_client.create_collection(name="documentation")

# Initialize Github client
g = Github(os.getenv('GITHUB_TOKEN'))

def crawl_documentation(url):
    def crawl_page(page_url, visited):
        if page_url in visited:
            return []
        
        visited.add(page_url)
        response = requests.get(page_url)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.find('body').get_text(separator='\n', strip=True)
        
        documents = [{
            'text': content,
            'metadata': {'url': page_url},
            'id': str(uuid.uuid4())
        }]

        # Find links to other pages within the same domain
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(page_url, href)
            if full_url.startswith(url) and full_url not in visited:
                documents.extend(crawl_page(full_url, visited))

        return documents

    visited = set()
    all_documents = crawl_page(url, visited)

    return {
        'text': [doc['text'] for doc in all_documents],
        'metadata': [doc['metadata'] for doc in all_documents],
        'ids': [doc['id'] for doc in all_documents]
    }

def fetch_github_issues(repo_url):
    # Extract owner and repo name from the URL
    _, _, owner, repo = repo_url.rstrip('/').rsplit('/', 3)

    repo = g.get_repo(f"{owner}/{repo}")
    issues = repo.get_issues(state='all')

    documents = []
    for issue in issues:
        content = f"Title: {issue.title}\nBody: {issue.body}"
        documents.append({
            'text': content,
            'metadata': {'url': issue.html_url, 'type': 'issue', 'number': issue.number},
            'id': str(uuid.uuid4())
        })

    return {
        'text': [doc['text'] for doc in documents],
        'metadata': [doc['metadata'] for doc in documents],
        'ids': [doc['id'] for doc in documents]
    }

def process_user_query(query):
    # Search the collection
    results = collection.query(
        query_texts=[query],
        n_results=3
    )

    # Process and format the results
    responses = []
    for i, (text, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
        response = f"Result {i+1}:\n"
        response += f"Source: {metadata['url']}\n"
        response += f"Content: {text[:500]}...\n\n"  # Truncate long texts
        responses.append(response)

    return "\n".join(responses)

def main():
    st.title("Documentation Assistant")

    # Sidebar
    with st.sidebar:
        st.header("Add New Documentation")
        with st.form("new_doc_form"):
            doc_url = st.text_input("Documentation URL")
            issues_url = st.text_input("GitHub Issues URL (optional)")
            submitted = st.form_submit_button("Add")
            
            if submitted:
                with st.spinner("Processing documentation..."):
                    # Process the new documentation
                    doc_data = crawl_documentation(doc_url)
                    collection.add(
                        documents=doc_data['text'],
                        metadatas=doc_data['metadata'],
                        ids=doc_data['ids']
                    )
                
                if issues_url:
                    with st.spinner("Fetching GitHub issues..."):
                        issues_data = fetch_github_issues(issues_url)
                        collection.add(
                            documents=issues_data['text'],
                            metadatas=issues_data['metadata'],
                            ids=issues_data['ids']
                        )
                
                st.success("Documentation added successfully!")

        st.header("Saved Documentation")
        # Display list of saved documentation here
        # (You may need to implement a way to keep track of added documentation)

    # Main chat interface
    st.header("Chat")
    user_query = st.text_input("Ask a question about the documentation:")
    if user_query:
        with st.spinner("Processing your query..."):
            response = process_user_query(user_query)
        st.write(response)

if __name__ == "__main__":
    main()