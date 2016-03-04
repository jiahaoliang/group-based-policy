
TOP_DIR=/home/stack/devstack
GBP_SCRIPT_DIR=$1
source $TOP_DIR/openrc admin admin
neutron net-create --router:external=true --shared ext-inet
neutron subnet-create --ip_version 4 --gateway 192.168.20.254 --name ext-inet-subnet1 --allocation-pool start=192.168.20.100,end=192.168.20.110 ext-inet 192.168.20.0/24

subnet_id=`neutron net-list | grep "ext-inet" | awk '{print $6}'`

sudo sed -i "s/^subnet_id=\".*\"/subnet_id=\"$subnet_id\"/g" $1/oc_gbp_params.sh
