from setuptools import setup, find_packages

setup(
    name="limbi",
    version="1.0.8",
    description="Omni-Agent Orchestration Platform — 87 specialised AI agents, any LLM provider.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Sayon Manna",
    license="Apache-2.0",
    python_requires=">=3.11",
    packages=find_packages(include=["limbi", "limbi.*"]),
    install_requires=[
        "click>=8.0",
        "rich>=13.0",
        "langchain-core>=0.3",
        "langchain-ollama>=0.2",
        "python-dotenv>=1.0",
    ],
    extras_require={
        "openai": ["langchain-openai>=0.2"],
        "anthropic": ["langchain-anthropic>=0.2"],
        "google": ["langchain-google-genai>=2.0"],
        "groq": ["langchain-groq>=0.2"],
        "mistral": ["langchain-mistralai>=0.2"],
        "cohere": ["langchain-cohere>=0.3"],
        "rag": ["chromadb>=0.5"],
        "aws": ["boto3>=1.34"],
        "server": [
            "fastapi>=0.115",
            "uvicorn>=0.30",
            "gradio>=4.0",
            "httpx>=0.27",
            "huggingface-hub>=0.24",
        ],
    },
    entry_points={
        "console_scripts": [
            "limbi=limbi.cli:main",
            "limbi-mcp=limbi.mcp_server:main_loop",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
