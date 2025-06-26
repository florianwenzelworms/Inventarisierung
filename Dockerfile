FROM python:3.10
WORKDIR /
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_DEBUG=TRUE

RUN apt-get update && apt-get install -y --no-install-recommends apt-utils
RUN apt-get update && \
    apt-get install -y \
        locales && \
    rm -r /var/lib/apt/lists/*

# RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
#     sed -i -e 's/# de_DE.UTF-8 UTF-8/de_DE.UTF-8 UTF-8/' /etc/locale.gen && \
#     dpkg-reconfigure --frontend=noninteractive locales

COPY requirements.txt requirements.txt
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

EXPOSE 3000
COPY . .

CMD ["flask", "run", "--host", "0.0.0.0", "--port", "3000"]