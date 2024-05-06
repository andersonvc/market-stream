FROM grafana/grafana:8.2.3
USER root
ADD ./provisioning /etc/grafana/provisioning
ADD ./dashboards /var/lib/grafana/dashboards
ADD ./grafana.ini /etc/grafana/grafana.ini
RUN chmod -R +rw /var/lib/grafana/dashboards