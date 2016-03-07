
TOP_DIR=$2
GBP_SCRIPT_DIR=$1
source $TOP_DIR/openrc admin admin
#set -x
serviceTenantID=`keystone tenant-list | grep "service" | awk '{print $2}'`
serviceRoleID=`keystone role-list | grep "service" | awk '{print $2}'`
adminRoleID=`keystone role-list | grep "admin" | awk '{print $2}'`
keystone user-role-add --user nova --tenant $serviceTenantID --role $serviceRoleID
sleep 1
keystone user-role-add --user neutron --tenant $serviceTenantID --role $adminRoleID
sleep 1



source $TOP_DIR/openrc neutron service
#source $TOP_DIR/keystonerc_neutron neutron service
neutron net-create --router:external=true --shared ext-inet
neutron subnet-create --ip_version 4 --gateway 192.168.104.254 --name ext-inet-subnet1 --allocation-pool start=192.168.104.111,end=192.168.104.120 ext-inet 192.168.104.0/24

subnet_id=`neutron net-list | grep "ext-inet" | awk '{print $6}'`

sudo sed -i "s/^subnet_id=\".*\"/subnet_id=\"$subnet_id\"/g" $1/oc_gbp_params.sh
