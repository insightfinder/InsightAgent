# InsightFinder vCenter Agent
This is the helm chart for Insightfinder vCenter agent. It can can be deployed to the Kubernetes cluster to collect data from vCenter API endpoint and send the data to InsightFinder application.

## Deployment
1. Create the namespace needed for this agent.
2. (Optional) Create imagePullSecret
If you are pulling the image from a private docker registry.
We need to create the image pull secret before we install this helm chart.
Here is the example command to load the local secret to Kubernetes secret:

```bash
kubectl create secret generic regcred \
    --from-file=.dockerconfigjson=<path/to/.docker/config.json> \
    --type=kubernetes.io/dockerconfigjson
```
You can also create the secret from scrath:

```bash
kubectl create secret docker-registry regcred \
  --docker-server=<your-registry-server>  \
  --docker-username=<your-name> \
  --docker-password=<your-pword> \
  --docker-email=<your-email>
```
3. Edit the `values.yaml` to config the vCenter info and Insightfinder endpoints.
4. Run helm install to deploy:
```bash
# For fresh installation
helm install --atomic -n <YOUR_NAMESPACE> my-vcenter-agent .

# For upgrade
helm upgrade --atomic -n <YOUR_NAMESPACE> my-vcenter-agent .
```
