# qa/qa_chain.py

from langchain.chains import SQLDatabaseChain
from langchain.chat_models import ChatOpenAI
from langchain.sql_database import SQLDatabase
from langchain.prompts.prompt import PromptTemplate

import psycopg2

db = SQLDatabase.from_uri("postgresql+psycopg2://python01_user51:python01_user51@123@110.41.115.206:8000/finance01")

import os




# 自定义 Prompt（可选，但推荐这样更贴合你课程语境）
DEFAULT_SQL_PROMPT = PromptTemplate.from_template("""
你是一个督学助教助手，帮助学生根据自然语言问题，从课程数据库中查询信息。
你只允许使用这些表：students, learning_tasks, student_tasks。

问题：{input}
请先生成 SQL，再执行查询，并提供自然语言回答。
""")


def get_sql_chain(verbose=True):
    """初始化 SQLDatabaseChain"""
    # 数据库连接（我们封装好了）
    db = SQLDatabase.from_uri("postgresql+psycopg2://python01_user51:python01_user51@123@110.41.115.206:8000/finance01")

    # 大模型
    llm = ChatOpenAI(temperature=0, model="deepseek")

    # 创建 Chain
    db_chain = SQLDatabaseChain.from_llm(
        llm=llm,
        db=db,
        prompt=DEFAULT_SQL_PROMPT,
        verbose=verbose,
        return_intermediate_steps=True
    )
    return db_chain


def run_sql_qa(question: str) -> str:
    """执行问答接口"""
    chain = get_sql_chain()
    result = chain.run(question)
    return result
