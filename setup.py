from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="wata-api",
    version="0.1.2",
    author="Павлючик Даниил",
    author_email="keemor821@gmail.com",
    description="Асинхронный клиент для работы с платежным API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/imdeniil/wata-client",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=[
        "aiohttp>=3.7.0",
        "cryptography>=3.4.0",
    ],
)