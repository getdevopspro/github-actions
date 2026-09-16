FROM alpine:3.22
ARG PACKAGE
ARG DEPENDENCY=1
RUN echo cache-fixture-dependency-${PACKAGE}-${DEPENDENCY} && sleep 5 && echo "${PACKAGE}:${DEPENDENCY}" > /dependency.txt
COPY ${PACKAGE}.txt /source.txt
RUN echo cache-fixture-source-${PACKAGE} && test -s /source.txt && cat /dependency.txt /source.txt > /result.txt
