from setuptools import setup, find_packages

setup(
    name="hermes-supabase-memory",
    version="1.0.0",
    description="Supabase memory plugin for Hermes Agent",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Antonov Salvarrey (@asalvarrey)",
    url="https://github.com/asalvarrey/Hermes-memory",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["supabase>=2.0.0"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
