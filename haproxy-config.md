# HAProxy Configuration for MQTT over SSL

This guide describes how to configure HAProxy to proxy your MQTT traffic securely over SSL/TLS.

## HAProxy Configuration

Add these sections to your existing HAProxy configuration:

```
# MQTT Frontend - SSL/TLS termination
frontend mqtt_frontend
    bind *:443 ssl crt /path/to/your/certificate.pem
    
    # ACL to detect MQTT WebSocket traffic
    acl is_mqtt_ws path_beg /mqtt
    
    # Route MQTT WebSocket traffic
    use_backend mqtt_ws_backend if is_mqtt_ws
    
    # Default backend for regular HTTP traffic
    default_backend web_backend

# MQTT WebSocket Backend
backend mqtt_ws_backend
    mode http
    option forwardfor
    
    # Enable WebSocket support
    option http-server-close
    option http-pretend-keepalive
    
    # Route to MQTT broker WebSocket port
    server mqtt_broker 127.0.0.1:9001
    
# Web Backend (FastAPI)
backend web_backend
    mode http
    option forwardfor
    
    # Route to FastAPI backend
    server fastapi 127.0.0.1:8001
```

## HAProxy SSL Configuration

For secure WebSockets (WSS), HAProxy needs your SSL certificate. Make sure your SSL certificate is in PEM format containing both the certificate and private key.

## MQTT Client Configuration

For connecting MQTT clients over secure WebSockets:

1. **Host**: Your domain (question-answer.jolomo.io)
2. **Port**: 443 (standard HTTPS port)
3. **Path**: /mqtt (for WebSocket connections)
4. **Protocol**: wss (WebSocket Secure)

## External MQTT Client Access

If you want to allow external MQTT clients to connect via plain TCP (port 1883), add this to your HAProxy config:

```
# MQTT TCP Frontend
frontend mqtt_tcp
    bind *:8883 ssl crt /path/to/your/certificate.pem
    mode tcp
    option tcplog
    
    # Route to MQTT TCP backend
    default_backend mqtt_tcp_backend
    
# MQTT TCP Backend
backend mqtt_tcp_backend
    mode tcp
    server mqtt_broker 127.0.0.1:1883
```

This will make your MQTT broker accessible via:
- Secure WebSockets (WSS): question-answer.jolomo.io:443/mqtt
- Secure MQTT (MQTTS): question-answer.jolomo.io:8883

## Security Considerations

1. Allow anonymous connections only for testing. For production, configure username/password authentication.
2. Keep your broker ports (1883, 9001) bound to localhost only, as shown in the docker-compose.yml file.
3. Configure appropriate ACLs in your MQTT broker to restrict topic access if needed.