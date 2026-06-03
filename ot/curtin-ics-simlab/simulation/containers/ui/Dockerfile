FROM python:3.13-slim

# Update
RUN apt-get update

RUN pip3 install requests
RUN pip3 install streamlit

# Set TERM environment variable
ENV TERM=xterm-256color
ENV FLASK_ENV=production
ENV STREAMLIT_LOG_LEVEL=error

# Copy container source code
WORKDIR /src
COPY ./src/ .