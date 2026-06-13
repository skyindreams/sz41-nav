FROM nginx:alpine
COPY . /usr/share/nginx/html
RUN chmod -R a+r /usr/share/nginx/html && find /usr/share/nginx/html -type d -exec chmod a+x {} \;
EXPOSE 80
