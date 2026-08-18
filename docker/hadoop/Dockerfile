FROM ghcr.io/apache/hadoop:3.4.3

USER root
COPY --chown=1000:100 core-site.xml hdfs-site.xml mapred-site.xml /opt/hadoop/etc/hadoop/
USER hadoop
