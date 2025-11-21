#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product Attachment 批量导入脚本
从 Excel 文件读取产品附件数据并导入到 Frappe
"""

import frappe
import pandas as pd
import os
from datetime import datetime

# 测试模式：设置为 None 则处理全部数据
TEST_LIMIT = 5  # 改为 None 以处理全部数据

def register_existing_file_to_frappe(file_path, file_name):
    """注册已存在的文件到Frappe文件系统（私有文件，不重新上传）"""
    try:
        # 构建 Frappe 私有文件的 URL
        # 从完整路径提取相对路径
        if 'download_files' in file_path:
            relative_filename = file_path.split('download_files/')[-1]
            file_url = f"/private/files/download_files/{relative_filename}"
        else:
            file_url = f"/private/files/{file_name}"
        
        # 检查是否已经存在相同文件的记录
        existing_file = frappe.db.exists("File", {"file_url": file_url})
        if existing_file:
            print(f"[INFO] 文件记录已存在: {file_url}")
            return file_url
        
        # 创建 File 记录（指向已存在的文件）
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "file_url": file_url,
            "is_private": 1,  # 私有文件
            "folder": "Home/Attachments"
        })
        
        file_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        print(f"[SUCCESS] 文件已注册: {file_url}")
        return file_url
        
    except Exception as e:
        error_msg = f"注册文件失败: {file_name}, 错误: {str(e)}"
        print(f"[ERROR] {error_msg}")
        frappe.log_error(error_msg, "File Registration Error")
        raise



def create_product_attachment(file_id, product_code, attachment_type, file_name, 
                              file_url, uploaded_by, uploaded_date, file_size, 
                              description):
    """创建 Product Attachment 记录"""
    try:
        attachment_doc = frappe.get_doc({
            "doctype": "Product Attachment",
            "file_id": file_id,
            "product_code": product_code,
            "attachment_type": attachment_type,
            "file_name": file_name,
            "attachment": file_url,
            "uploaded_by": uploaded_by,
            "uploaded_date": uploaded_date,
            "file_size": file_size,
            "description": description
        })
        
        attachment_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        print(f"[SUCCESS] Product Attachment 已创建: {product_code} - {file_name}")
        return True
        
    except Exception as e:
        error_msg = f"创建 Product Attachment 失败: {product_code}, 文件: {file_name}, 错误: {str(e)}"
        print(f"[ERROR] {error_msg}")
        frappe.log_error(error_msg, "Product Attachment Creation Error")
        return False


def parse_article_numbers(article_numbers_str):
    """解析并清理 Article Numbers"""
    if pd.isna(article_numbers_str) or not article_numbers_str:
        return []
    
    # 分割并清理每个 Article Number
    article_numbers = [num.strip() for num in str(article_numbers_str).split(',')]
    # 过滤空字符串
    article_numbers = [num for num in article_numbers if num]
    
    return article_numbers


def get_file_size_mb(file_path):
    """获取文件大小（MB）"""
    try:
        size_bytes = os.path.getsize(file_path)
        size_mb = size_bytes / (1024 * 1024)
        return round(size_mb, 2)
    except:
        return 0


def process_excel_row(row, base_path):
    """处理单行 Excel 数据"""
    try:
        # 提取字段
        file_id = row.get('No.', '')
        filename = row.get('Filename', '')
        file_size = row.get('File Size', '')
        attachment_type = row.get('Type', '')
        uploaded_date = row.get('Uploaded Date', '')
        uploaded_by = row.get('Uploaded By', '')
        article_numbers_str = row.get('Article Numbers', '')
        download_status = row.get('Download Status', '')
        local_path = row.get('Local Path', '')
        
        # 打印调试信息
        print(f"\n[INFO] ========== 处理记录 ==========")
        print(f"[INFO] No: {file_id}")
        print(f"[INFO] Filename: {filename}")
        print(f"[INFO] File Size: {file_size}")
        print(f"[INFO] Type: {attachment_type}")
        print(f"[INFO] Article Numbers: {article_numbers_str}")
        print(f"[INFO] Local Path: {local_path}")
        
        # 验证必要字段
        if pd.isna(filename) or not filename:
            print(f"[SKIP] 文件名为空，跳过此行")
            return False
        
        if pd.isna(local_path) or not local_path:
            print(f"[SKIP] 本地路径为空，跳过此行")
            return False
        
        # 解析 Article Numbers
        article_numbers = parse_article_numbers(article_numbers_str)
        if not article_numbers:
            print(f"[SKIP] Article Numbers 为空，跳过此行")
            return False
        
        print(f"[INFO] 解析到 {len(article_numbers)} 个 Article Numbers: {article_numbers}")
        
        # 构建完整文件路径
        local_path_normalized = str(local_path).replace('\\', '/')
        full_file_path = os.path.join(base_path, local_path_normalized)
        
        # 检查文件是否存在
        if not os.path.exists(full_file_path):
            print(f"[ERROR] 文件不存在: {full_file_path}")
            return False
        
        print(f"[INFO] 文件路径: {full_file_path}")
        
        # 注册文件到 Frappe
        try:
            file_url = register_existing_file_to_frappe(full_file_path, filename)
        except Exception as e:
            print(f"[ERROR] 注册文件失败: {str(e)}")
            frappe.db.rollback()
            return False
        
        # 为每个 Article Number 创建 Product Attachment 记录
        success_count = 0
        for article_number in article_numbers:
            try:
                result = create_product_attachment(
                    file_id=file_id,
                    product_code=article_number,
                    attachment_type=attachment_type,
                    file_name=filename,
                    file_url=file_url,
                    uploaded_by=uploaded_by,
                    uploaded_date=uploaded_date,
                    file_size=file_size,
                    description=article_numbers_str  # 保留原始的 Article Numbers 字符串
                )
                if result:
                    success_count += 1
            except Exception as e:
                print(f"[ERROR] 创建 Product Attachment 失败: {article_number}, 错误: {str(e)}")
                frappe.db.rollback()
        
        print(f"[INFO] 成功创建 {success_count}/{len(article_numbers)} 条 Product Attachment 记录")
        return success_count > 0
        
    except Exception as e:
        print(f"[ERROR] 处理行数据失败: {str(e)}")
        frappe.db.rollback()
        return False


def main():
    """主函数"""
    # 初始化 Frappe
    frappe.init(site='sos.byrydens.com')
    frappe.connect()
    
    try:
        # Excel 文件路径
        excel_path = '/home/frappe/frappe-bench/temp/product_data.xlsx'
        # 文件基础路径
        base_path = '/home/frappe/frappe-bench/sites/assets'
        
        print(f"[INFO] 开始读取 Excel 文件: {excel_path}")
        
        # 读取 Excel 文件
        df = pd.read_excel(excel_path)
        
        print(f"[INFO] Excel 文件共有 {len(df)} 行数据")
        print(f"[INFO] 列名: {df.columns.tolist()}")
        
        # 测试模式：限制处理行数
        if TEST_LIMIT is not None:
            df = df.head(TEST_LIMIT)
            print(f"[INFO] 测试模式：仅处理前 {TEST_LIMIT} 行")
        
        # 为排序准备：计算文件大小（MB）
        file_sizes = []
        for idx, row in df.iterrows():
            local_path = row.get('Local Path', '')
            if pd.isna(local_path) or not local_path:
                file_sizes.append(0)
                continue
            
            local_path_normalized = str(local_path).replace('\\', '/')
            full_file_path = os.path.join(base_path, local_path_normalized)
            file_size_mb = get_file_size_mb(full_file_path)
            file_sizes.append(file_size_mb)
        
        df['file_size_mb'] = file_sizes
        
        # 按文件大小降序排序（大文件优先）
        df = df.sort_values('file_size_mb', ascending=False)
        print(f"[INFO] 已按文件大小排序（大文件优先）")
        
        # 处理每一行
        success_count = 0
        failure_count = 0
        
        for idx, row in df.iterrows():
            print(f"\n[INFO] ========================================")
            print(f"[INFO] 处理第 {idx + 1}/{len(df)} 行")
            
            result = process_excel_row(row, base_path)
            
            if result:
                success_count += 1
            else:
                failure_count += 1
        
        # 打印汇总信息
        print(f"\n[INFO] ========================================")
        print(f"[INFO] 导入完成！")
        print(f"[INFO] 成功: {success_count} 行")
        print(f"[INFO] 失败: {failure_count} 行")
        print(f"[INFO] ========================================")
        
    except Exception as e:
        print(f"[ERROR] 主函数执行失败: {str(e)}")
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == '__main__':
    main()
