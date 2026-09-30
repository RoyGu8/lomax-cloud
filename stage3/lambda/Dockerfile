FROM public.ecr.aws/lambda/python:3.13

RUN pip install Pillow -t ${LAMBDA_TASK_ROOT}

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]
