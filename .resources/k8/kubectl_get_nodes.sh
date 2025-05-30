kubectl get nodes
kubectl create deployment nginx-test --image=nginx:alpine
kubectl scale deployment nginx-test --replicas=2
kubectl get pods -o wide
kubectl expose deployment nginx-test --type=NodePort --port=80 --target-port=80
kubectl delete deployment nginx-test

