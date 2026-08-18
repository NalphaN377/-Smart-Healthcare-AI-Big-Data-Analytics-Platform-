FROM apache/spark:4.1.1-python3

USER root
COPY --chown=185:0 docker/hadoop/core-site.xml docker/hadoop/hdfs-site.xml docker/hadoop/mapred-site.xml /opt/spark/conf/
COPY --chown=185:0 spark/jobs/ /opt/medical/jobs/
RUN mkdir -p /opt/spark/.ivy2.5.2 && chown -R 185:0 /opt/spark/.ivy2.5.2
USER spark
