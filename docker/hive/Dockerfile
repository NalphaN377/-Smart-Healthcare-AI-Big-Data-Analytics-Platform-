FROM apache/hive:4.1.0

USER root
COPY --chown=1000:0 hadoop/core-site.xml hadoop/hdfs-site.xml hadoop/mapred-site.xml hive/hive-site.xml /opt/hive/conf/
COPY --chown=1000:0 hive/init.sql hive/verify.sql /opt/medical/hive/
USER hive
