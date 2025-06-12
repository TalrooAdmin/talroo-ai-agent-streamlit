from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, FewShotChatMessagePromptTemplate
from langchain.chains import create_retrieval_chain, create_history_aware_retriever
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from config import answer_examples

store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def get_llm():
    return ChatOpenAI(model="gpt-4o-mini")


def get_dictionary_chain():

    dictionary = ['word indicate job link or application  -> link',
                  'word indicate job location -> location',
                  'word indicate job title -> title',
                  'word indicate job description -> description',
                  'word indicate job requirements -> requirements',
                  'word indicate job benefits -> benefits',
                  'word indicate job salary -> salary',
                  'word indicate job type -> type',]
    llm = get_llm()
    prompt = ChatPromptTemplate.from_template(
        f"""
        Identify the user's question and update user's question based on our dictionary
        If you don't think we don't need to update user's question, return the same question
        :
        User's question: {{question}}
        Dictionary: {dictionary}
        """
    )

    dictionary_chain = prompt | llm | StrOutputParser()
    return dictionary_chain


def get_retriever():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    index_name = 'nurse-jobs2'
    vector_store = PineconeVectorStore.from_existing_index(index_name=index_name, embedding=embeddings)
    retriever = vector_store.as_retriever(search_kwargs={"k": 6})
    return retriever

def get_history_retriever():
    llm = get_llm()
    retriever = get_retriever()
    
    contextualize_q_system_prompt = (
        "Given a chat history and the latest user question "
        "which might reference contxt in the chat history."
        "formulate a standalone question which can be understood"
        "without the chat history. Do No answer the question, "
        "just reformulate it if needed and otherwise return it as is."
    )

    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )
    history_awware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)
    return history_awware_retriever


def get_rag_chain():
    llm = get_llm()

    example_prompt = ChatPromptTemplate.from_messages(
        [
            ("human", "{input}"),
            ("ai", "{answer}")
        ]
    )
    few_shot_prompt = FewShotChatMessagePromptTemplate(
        example_prompt=example_prompt,
        examples = answer_examples
    )

    system_prompt = (
        "You are an intelligent job-search assistant. "
        "For general questions about jobs, fetch and use information from the jobs database. "
        "When a user asks for job recommendations, return up to three of the most similar positions. "
        "Keep all answers concise—no more than three sentences. "
        "If you don’t know the answer, honestly say you don’t know."
        "Do not suggest to go other job search website."
        "\n\n"
        "{context}"
    )

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        few_shot_prompt,
        MessagesPlaceholder("chat_history"),
        ("human", "{input}")
    ])


    history_awware_retriever = get_history_retriever()

    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

    rag_chain = create_retrieval_chain(history_awware_retriever, question_answer_chain)

    conversation_rag_chain = RunnableWithMessageHistory(
        rag_chain, 
        get_session_history, 
        input_messages_key="input", 
        history_messages_key="chat_history",
        output_messages_key="answer" ).pick("answer")

    return conversation_rag_chain


def get_ai_response(user_message):
    load_dotenv()
    dictionary_chain = get_dictionary_chain()
    rag_chain = get_rag_chain()
    resume_chain = {"input": dictionary_chain} | rag_chain
    ai_response = resume_chain.stream(
        {"question": user_message},
        config={"configurable": {"session_id": "1"}})
    return ai_response