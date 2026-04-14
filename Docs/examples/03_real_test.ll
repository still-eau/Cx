; ModuleID = '<string>'
source_filename = "<string>"
target datalayout = "e-m:w-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-windows-msvc"

%Node.0 = type { i32, ptr }
%enum.Status.1 = type { i32, [32 x i8] }

@str_8112326645128557908 = internal constant [17 x i8] c"Value is correct\00"
@str_4359137798212553189 = internal constant [15 x i8] c"Value is wrong\00"
@str_2450913464318705929 = internal constant [9 x i8] c"Looping:\00"
@str_7166281546816972129 = internal constant [15 x i8] c"Loop iteration\00"
@str_6299993770278093445 = internal constant [13 x i8] c"Status is OK\00"
@str_509501428449311751 = internal constant [8 x i8] c"Error: \00"

define i32 @main() {
entry_0:
  %t0 = alloca ptr, align 8
  %t2 = call ptr @malloc(i32 1)
  store ptr %t2, ptr %t0, align 8
  %t3 = load ptr, ptr %t0, align 8
  %t4 = getelementptr %Node.0, ptr %t3, i32 0, i32 0
  %t4.cast = bitcast ptr %t4 to ptr
  store i32 42, ptr %t4.cast, align 4
  %t6 = load ptr, ptr %t0, align 8
  %t7 = getelementptr %Node.0, ptr %t6, i32 0, i32 1
  %t7.cast = bitcast ptr %t7 to ptr
  %.4 = bitcast ptr null to ptr
  store ptr %.4, ptr %t7.cast, align 8
  %t9 = alloca { ptr, i64 }, align 8
  %t10 = load ptr, ptr %t0, align 8
  %t11 = getelementptr %Node.0, ptr %t10, i32 0, i32 0
  %t11.cast = bitcast ptr %t11 to ptr
  %t12 = load i32, ptr %t11.cast, align 4
  %t14 = icmp eq i32 %t12, 42
  %t15 = alloca { ptr, i64 }, align 8
  br i1 %t14, label %if_then_1, label %if_else_2

if_then_1:                                        ; preds = %entry_0
  %.7 = bitcast ptr @str_8112326645128557908 to ptr
  %.8 = insertvalue { ptr, i64 } undef, ptr %.7, 0
  %t16 = insertvalue { ptr, i64 } %.8, i64 16, 1
  store { ptr, i64 } %t16, ptr %t15, align 8
  br label %if_merge_3

if_else_2:                                        ; preds = %entry_0
  %.11 = bitcast ptr @str_4359137798212553189 to ptr
  %.12 = insertvalue { ptr, i64 } undef, ptr %.11, 0
  %t17 = insertvalue { ptr, i64 } %.12, i64 14, 1
  store { ptr, i64 } %t17, ptr %t15, align 8
  br label %if_merge_3

if_merge_3:                                       ; preds = %if_else_2, %if_then_1
  %t18 = load { ptr, i64 }, ptr %t15, align 8
  store { ptr, i64 } %t18, ptr %t9, align 8
  %t19 = load { ptr, i64 }, ptr %t9, align 8
  call void @print({ ptr, i64 } %t19)
  %.17 = bitcast ptr @str_2450913464318705929 to ptr
  %.18 = insertvalue { ptr, i64 } undef, ptr %.17, 0
  %t21 = insertvalue { ptr, i64 } %.18, i64 8, 1
  call void @print({ ptr, i64 } %t21)
  %t25 = alloca i32, align 4
  store i32 0, ptr %t25, align 4
  br label %range_cond_4

range_cond_4:                                     ; preds = %range_body_5, %if_merge_3
  %t26 = load i32, ptr %t25, align 4
  %t27 = icmp ule i32 %t26, 3
  br i1 %t27, label %range_body_5, label %range_end_6

range_body_5:                                     ; preds = %range_cond_4
  %.23 = bitcast ptr @str_7166281546816972129 to ptr
  %.24 = insertvalue { ptr, i64 } undef, ptr %.23, 0
  %t28 = insertvalue { ptr, i64 } %.24, i64 14, 1
  call void @print({ ptr, i64 } %t28)
  %t31 = add i32 %t26, 1
  store i32 %t31, ptr %t25, align 4
  br label %range_cond_4

range_end_6:                                      ; preds = %range_cond_4
  %t32 = alloca %enum.Status.1, align 8
  %t33 = alloca %enum.Status.1, align 8
  %t34 = getelementptr %enum.Status.1, ptr %t33, i32 0, i32 0
  %t34.cast = bitcast ptr %t34 to ptr
  store i32 1, ptr %t34.cast, align 4
  %t36 = load %enum.Status.1, ptr %t33, align 4
  store %enum.Status.1 %t36, ptr %t32, align 4
  %t37 = load %enum.Status.1, ptr %t32, align 4
  %spill.t37 = alloca %enum.Status.1, align 8
  store %enum.Status.1 %t37, ptr %spill.t37, align 4
  %t38 = getelementptr %enum.Status.1, ptr %spill.t37, i32 0, i32 0
  %t38.cast = bitcast ptr %t38 to ptr
  %t39 = load i32, ptr %t38.cast, align 4
  %t40 = icmp eq i32 %t39, 0
  br i1 %t40, label %arm_8, label %next_arm_9

arm_8:                                            ; preds = %range_end_6
  %.32 = bitcast ptr @str_6299993770278093445 to ptr
  %.33 = insertvalue { ptr, i64 } undef, ptr %.32, 0
  %t42 = insertvalue { ptr, i64 } %.33, i64 12, 1
  call void @print({ ptr, i64 } %t42)
  br label %match_merge_7

next_arm_9:                                       ; preds = %range_end_6
  %t44 = icmp eq i32 %t39, 1
  br i1 %t44, label %arm_10, label %next_arm_11

arm_10:                                           ; preds = %next_arm_9
  %.37 = bitcast ptr @str_509501428449311751 to ptr
  %.38 = insertvalue { ptr, i64 } undef, ptr %.37, 0
  %t47 = insertvalue { ptr, i64 } %.38, i64 7, 1
  call void @print({ ptr, i64 } %t47)
  %t49 = load { ptr, i64 }, ptr %t9, align 8
  call void @print({ ptr, i64 } %t49)
  br label %match_merge_7

next_arm_11:                                      ; preds = %next_arm_9
  br label %match_merge_7

match_merge_7:                                    ; preds = %next_arm_11, %arm_10, %arm_8
  %t51 = load ptr, ptr %t0, align 8
  call void @free(ptr %t51)
  ret i32 0

dead_12:                                          ; No predecessors!
  ret i32 0
}

declare ptr @malloc(i32)

declare void @print({ ptr, i64 })

declare void @free(ptr)
