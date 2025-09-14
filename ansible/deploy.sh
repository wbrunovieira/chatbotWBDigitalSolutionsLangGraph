#!/bin/bash

# WB Digital Solutions Chatbot - Deploy Script
# This script deploys the chatbot to the production server

set -e

echo "================================================"
echo "WB Digital Solutions Chatbot - Deploy Script"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if ansible is installed
if ! command -v ansible &> /dev/null; then
    echo -e "${RED}Ansible is not installed. Please install it first.${NC}"
    echo "Run: pip install ansible"
    exit 1
fi

# Check if inventory file exists
if [ ! -f "inventory.ini" ]; then
    echo -e "${RED}inventory.ini not found!${NC}"
    echo "Please ensure you're running this script from the ansible directory."
    exit 1
fi

# Check environment variables
echo -e "${YELLOW}Checking configuration...${NC}"
if grep -q "YOUR_DEEPSEEK_API_KEY" inventory.ini; then
    echo -e "${RED}Please update the DEEPSEEK_API_KEY in inventory.ini${NC}"
    exit 1
fi

# Prompt for confirmation
echo ""
echo -e "${YELLOW}This will deploy the chatbot to the production server.${NC}"
echo "Server: 45.90.123.190"
echo "Domain: chatbot.wbdigitalsolutions.com"
echo ""
read -p "Do you want to continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 1
fi

# Run ansible playbook
echo ""
echo -e "${GREEN}Starting deployment...${NC}"
ansible-playbook -i inventory.ini playbook.yml -v

# Check deployment status
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Deployment completed successfully!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo "Your chatbot is now available at:"
    echo "https://chatbot.wbdigitalsolutions.com"
    echo ""
    echo "To check the status, SSH to the server and run:"
    echo "docker ps | grep wb_chatbot"
    echo ""
else
    echo ""
    echo -e "${RED}================================================${NC}"
    echo -e "${RED}Deployment failed. Please check the logs above.${NC}"
    echo -e "${RED}================================================${NC}"
    exit 1
fi