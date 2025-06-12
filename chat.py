from llm import get_ai_response
import streamlit as st

#page config

st.set_page_config(
    page_title="Job Search AI Agent",
    page_icon="🤖",
)

st.title("Job Search AI Agent")
st.caption("Please type your job search query")

if 'message_list' not in st.session_state:
    st.session_state.message_list = []

print('before',st.session_state.message_list)

for message in st.session_state.message_list:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if user_question:= st.chat_input(placeholder="Please type your job search query"):
    with st.chat_message("user"):
        st.write(user_question)
    st.session_state.message_list.append({"role": "user", "content": user_question})

    with st.spinner("Answering..."):
        ai_response = get_ai_response(user_question)
        with st.chat_message("ai"):
            ai_message = st.write_stream(ai_response)
        st.session_state.message_list.append({"role": "ai", "content": ai_message})

print('after',st.session_state.message_list)