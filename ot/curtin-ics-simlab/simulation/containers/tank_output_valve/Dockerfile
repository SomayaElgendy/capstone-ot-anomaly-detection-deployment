FROM python:3.13-slim

# Update pip
RUN pip install --upgrade pip

# Install required Python packages
RUN pip3 install pymodbus==3.11.1
RUN pip3 install pyserial
RUN pip3 install numpy
RUN pip3 install flask
RUN pip3 install redis==5.0.1 

# Set environment variables
ENV TERM=xterm-256color
ENV FLASK_ENV=production
ENV STREAMLIT_LOG_LEVEL=error

# Copy container source code
WORKDIR /src
COPY ./src/ .
