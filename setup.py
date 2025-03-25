from setuptools import setup, find_packages

setup(
    name="resource_manager",
    version="0.1.0",
    packages=find_packages(include=["resource_manager", "resource_manager.*"]),
    install_requires=[
        "requests>=2.0.0",
    ],
    extras_require={
        "server": ["Flask>=2.0.0"],
    },
    author="Murilo Teixeira <dev@murilo.etc.br>",
    description="Client module for the Resource Manager API. Server code is available as an extra.",
)
