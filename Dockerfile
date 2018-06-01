FROM python:3.6-alpine

# Install system packages
RUN apk add --update \
        gcc \
        g++ \
        libc-dev \
        linux-headers \
        zip \
        make && \
    rm -rf /var/cache/apk/*

WORKDIR /opt/python/app/

# Install Python requirements.
RUN pip install --upgrade pip
COPY ./requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Copy setup scripts and files.
COPY ./bootstrap.sh bootstrap.sh
COPY ./policy.json policy.json
COPY ./role.json role.json
COPY ./Makefile Makefile
RUN chmod +x bootstrap.sh

# Copy tests.
COPY ./.pylintrc .pylintrc
COPY ./test test/

# Copy application files.
COPY ./lambda lambda/

# Create sym link to site-packages dir.
RUN cd lambda && \
    ln -s \
        `python -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())"` \
        packages

CMD ["ls", "-a"]
