#!/usr/bin/env python3
"""
Token统计查看器
用于查看LLM token使用量统计
"""

import json
import os
import sys
from datetime import datetime

def format_number(num):
    """格式化数字，添加千分位分隔符"""
    return f"{num:,}"

def format_cost(cost):
    """格式化成本"""
    return f"${cost:.4f}"

def view_token_stats(stats_file):
    """查看token统计"""
    if not os.path.exists(stats_file):
        print(f"❌ 统计文件不存在: {stats_file}")
        return
    
    try:
        with open(stats_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        summary = data.get("summary", {})
        model_usage = data.get("model_usage", {})
        cost_estimation = data.get("cost_estimation", {})
        
        print("=" * 60)
        print("🔥 LLM TOKEN 使用统计")
        print("=" * 60)
        
        # 基本信息
        print("\n📊 基本信息:")
        print(f"  开始时间: {summary.get('start_time', 'N/A')}")
        print(f"  最后更新: {summary.get('last_update', 'N/A')}")
        print(f"  运行时间: {summary.get('runtime', 'N/A')}")
        print(f"  总请求数: {format_number(summary.get('request_count', 0))}")
        
        # Token使用量
        print("\n🎯 Token 使用量:")
        print(f"  输入Token:  {format_number(summary.get('total_input_tokens', 0))}")
        print(f"  输出Token:  {format_number(summary.get('total_output_tokens', 0))}")
        print(f"  总Token:    {format_number(summary.get('total_tokens', 0))}")
        
        # 平均值
        request_count = summary.get('request_count', 0)
        if request_count > 0:
            avg_input = summary.get('total_input_tokens', 0) / request_count
            avg_output = summary.get('total_output_tokens', 0) / request_count
            avg_total = summary.get('total_tokens', 0) / request_count
            
            print(f"\n📈 平均值 (每次请求):")
            print(f"  平均输入Token: {avg_input:.1f}")
            print(f"  平均输出Token: {avg_output:.1f}")
            print(f"  平均总Token:   {avg_total:.1f}")
        
        # 按模型统计
        if model_usage:
            print(f"\n🤖 按模型统计:")
            for model, usage in model_usage.items():
                print(f"  {model}:")
                print(f"    请求数:     {format_number(usage.get('requests', 0))}")
                print(f"    输入Token:  {format_number(usage.get('input_tokens', 0))}")
                print(f"    输出Token:  {format_number(usage.get('output_tokens', 0))}")
                print(f"    总Token:    {format_number(usage.get('total_tokens', 0))}")
                
                if usage.get('requests', 0) > 0:
                    avg_per_req = usage.get('total_tokens', 0) / usage['requests']
                    print(f"    平均Token:  {avg_per_req:.1f}")
                print()
        
        # 成本估算
        if cost_estimation:
            print(f"💰 成本估算 (USD):")
            total_cost = 0
            for model, cost in cost_estimation.items():
                print(f"  {model}: {format_cost(cost)}")
                total_cost += cost
            print(f"  总估算成本: {format_cost(total_cost)}")
        
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 读取统计文件时出错: {e}")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        stats_file = sys.argv[1]
    else:
        # 默认路径
        default_dir = "exec_output_llamatouch_RASSDroid_deepseek_09-20"
        stats_file = os.path.join(default_dir, "llm_token_usage.json")
    
    view_token_stats(stats_file)

if __name__ == "__main__":
    main()